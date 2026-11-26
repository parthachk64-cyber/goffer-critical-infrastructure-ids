"""End-to-end run: ingest -> prepare -> detect -> triage -> record response -> evaluate -> report."""

from __future__ import annotations

import json
import platform
import subprocess
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

import pandas as pd

from infra_ids import __version__
from infra_ids.detectors import rule_reasons
from infra_ids.evaluate import hardware_info, metrics_table, time_inference
from infra_ids.ingest import load_csv
from infra_ids.response import AnalystQueue, SimClock, apply_demo_policy
from infra_ids.splits import feature_hash, overlap_report, split_manifest
from infra_ids.train import MODEL_ORDER, deviation_codes, train
from infra_ids.triage import build_alerts, write_alerts

ALERT_MODEL = "hybrid_iso_rule"
LATENCY_BATCH, LATENCY_WARMUP, LATENCY_REPEATS = 256, 5, 30
SIM_START = datetime(2000, 1, 1, tzinfo=UTC)  # arbitrary epoch: simulated times are not calendar facts


def _dep_versions() -> dict[str, str]:
    out = {}
    for pkg in ("numpy", "pandas", "scikit-learn", "matplotlib"):
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            out[pkg] = "unavailable"
    return out


def _source_revision() -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent, capture_output=True, text=True, timeout=5, check=False
        )
        return res.stdout.strip() if res.returncode == 0 and res.stdout.strip() else "unversioned"
    except (OSError, subprocess.SubprocessError):
        return "unversioned"


def new_run_dir(out_base: Path, seed: int) -> Path:
    """Create a fresh run directory; an existing run is never overwritten."""
    out_base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id, n = f"{stamp}-s{seed}", 1
    while (out_base / run_id).exists():
        n += 1
        run_id = f"{stamp}-s{seed}-{n}"
    run_dir = out_base / run_id
    run_dir.mkdir()
    (out_base / "LATEST").write_text(run_id + "\n", encoding="utf-8")
    return run_dir


def run_experiment(
    train_csv: str | Path,
    test_csv: str | Path,
    seed: int,
    out_base: str | Path,
    dataset_label: str,
    max_alerts: int | None = 5000,
    val_fraction: float = 0.2,
    notes: list[str] | None = None,
) -> Path:
    from infra_ids.report import write_report

    tr, te = load_csv(train_csv, "train"), load_csv(test_csv, "test")
    overlap = overlap_report(tr.frame, te.frame)
    bundle, _val = train(tr.frame, seed, val_fraction)

    test = te.frame
    X_test = bundle.pre.transform(test)
    scores = bundle.score_all(X_test, test)
    dup = feature_hash(test).isin(set(feature_hash(tr.frame))).astype(int).to_numpy()

    pred = pd.DataFrame({"row_id": test["row_id"], "y_true": test["label"], "attack_cat": test["attack_cat"],
                         "train_duplicate": dup})  # fmt: skip
    for m in MODEL_ORDER:
        pred[f"score_{m}"] = scores[m]
        pred[f"pred_{m}"] = (scores[m] >= bundle.thresholds[m]).astype(int)

    meaningful = {m: bundle.detectors[m].meaningful_scores for m in MODEL_ORDER}
    metrics = pd.DataFrame(metrics_table(pred, bundle.thresholds, meaningful, MODEL_ORDER))

    run_dir = new_run_dir(Path(out_base), seed)
    pred.to_csv(run_dir / "predictions.csv", index=False, float_format="%.6f", lineterminator="\n")
    metrics.to_csv(run_dir / "metrics.csv", index=False, lineterminator="\n")

    latency = _measure_latency(bundle, test, X_test)
    (run_dir / "latency.json").write_text(json.dumps(latency, indent=2), encoding="utf-8")

    alert_rule_codes = rule_reasons(test)
    alerts, alert_info = build_alerts(
        test["row_id"].to_numpy(), scores[ALERT_MODEL], bundle.thresholds[ALERT_MODEL], ALERT_MODEL,
        bundle.version, lambda i: alert_rule_codes[i] + deviation_codes(bundle, X_test[i]), max_alerts,
    )  # fmt: skip
    write_alerts(run_dir / "alerts.jsonl", alerts)
    clock = SimClock(SIM_START, seed)
    queue = AnalystQueue(run_dir / "queue.jsonl", clock=clock)
    queue_summary = apply_demo_policy(queue, alerts)
    queue_summary["simulated_total_delay_s"] = clock.total_simulated_s

    manifest = {
        "run_id": run_dir.name,
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "dataset_label": dataset_label,
        "seed": seed,
        "package_version": __version__,
        "model_version": bundle.version,
        "source_revision": _source_revision(),
        "python": platform.python_version(),
        "dependencies": _dep_versions(),
        "inputs": {"train": tr.manifest, "test": te.manifest},
        "split": split_manifest(bundle.fit_n, bundle.val_n, len(test), val_fraction, seed),
        "duplicate_overlap": overlap,
        "preprocessing": bundle.pre.describe(),
        "positive_class": "label == 1 (attack)",
        "models": {m: {"config": bundle.detectors[m].config(), "threshold": bundle.thresholds[m],
                       "meaningful_scores": meaningful[m]} for m in MODEL_ORDER},
        "threshold_rule": "maximise F1 on validation rows; ties to the higher threshold; reference models use 0.5 on a fixed score",
        "alerts": {"model": ALERT_MODEL, **alert_info},
        "analyst_queue": {"policy": "SIMULATED: escalate if a rule reason code is present, else dismiss; no labels used", **queue_summary},
        "notes": notes or [],
    }  # fmt: skip
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    write_report(run_dir)
    return run_dir


def _measure_latency(bundle, test: pd.DataFrame, X_test) -> dict:
    n = min(LATENCY_BATCH, len(test))
    raw, X = test.iloc[:n], X_test[:n]
    out = {"hardware": hardware_info(), "batch_size": n, "unit": "milliseconds per batch (wall clock)",
           "excludes": "simulated analyst delay; model fitting; disk I/O", "preprocessing": time_inference(
               lambda b: bundle.pre.transform(b), raw, LATENCY_WARMUP, LATENCY_REPEATS), "models": {}}  # fmt: skip
    for m in MODEL_ORDER:
        det = bundle.detectors[m]
        out["models"][m] = time_inference(lambda _b, d=det: d.score(X, raw), None, LATENCY_WARMUP, LATENCY_REPEATS)
    return out
