"""Regenerate metrics, plots and report.md from a run's saved predictions and manifest only."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import precision_recall_curve  # noqa: E402

from infra_ids.evaluate import metrics_table  # noqa: E402
from infra_ids.train import MODEL_ORDER  # noqa: E402

LABELS = {
    "synthetic": "SYNTHETIC DEMONSTRATION (seeded generator; not real traffic)",
    "unsw": "INDEPENDENT BENCHMARK: UNSW-NB15 official partitions",
}


def resolve_run(path: str | Path) -> Path:
    """Accept a run directory, or a base directory holding a LATEST pointer."""
    p = Path(path)
    if (p / "manifest.json").exists():
        return p
    latest = p / "LATEST"
    if latest.exists():
        run = p / latest.read_text(encoding="utf-8").strip()
        if (run / "manifest.json").exists():
            return run
    subs = sorted(d for d in p.iterdir() if d.is_dir() and (d / "manifest.json").exists()) if p.is_dir() else []
    if subs:  # a directory of runs without a LATEST pointer: run ids start with a UTC timestamp, so the last sorts newest
        return subs[-1]
    raise FileNotFoundError(f"no run found at {path} (expected manifest.json or a LATEST pointer)")


def _fmt(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "n/a"
    return f"{v:.4f}" if isinstance(v, float) else str(v)


def _plot_confusion(pred: pd.DataFrame, manifest: dict, path: Path) -> None:
    models = list(MODEL_ORDER)
    fig, axes = plt.subplots(2, 3, figsize=(11, 7))
    for ax, m in zip(axes.ravel(), models, strict=True):
        y, p = pred["y_true"].to_numpy(), pred[f"pred_{m}"].to_numpy()
        cm = np.array([[((y == 0) & (p == 0)).sum(), ((y == 0) & (p == 1)).sum()],
                       [((y == 1) & (p == 0)).sum(), ((y == 1) & (p == 1)).sum()]])  # fmt: skip
        ax.imshow(cm, cmap="Blues")
        for (i, j), v in np.ndenumerate(cm):
            ax.text(j, i, f"{v:,}", ha="center", va="center", color="white" if v > cm.max() / 2 else "black")
        ax.set_xticks([0, 1], ["pred normal", "pred attack"])
        ax.set_yticks([0, 1], ["true normal", "true attack"])
        ax.set_title(m, fontsize=10)
    fig.suptitle(f"Confusion matrices, held-out test n={len(pred):,} ({manifest['dataset_label']})")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _plot_pr(pred: pd.DataFrame, manifest: dict, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6.5, 5))
    y = pred["y_true"].to_numpy()
    for m in MODEL_ORDER:
        if not manifest["models"][m]["meaningful_scores"] or y.min() == y.max():
            continue
        prec, rec, _ = precision_recall_curve(y, pred[f"score_{m}"])
        ax.plot(rec, prec, label=m)
    ax.axhline(y.mean(), color="grey", ls=":", label=f"prevalence {y.mean():.2f}")
    ax.set_xlabel("recall")
    ax.set_ylabel("precision")
    ax.set_title(f"Precision-recall, held-out test n={len(pred):,}\n{manifest['dataset_label']}", fontsize=10)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _table(df: pd.DataFrame, cols: list[str]) -> str:
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(_fmt(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def write_report(run_dir: str | Path) -> Path:
    run = Path(run_dir)
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    pred = pd.read_csv(run / "predictions.csv")
    thresholds = {m: manifest["models"][m]["threshold"] for m in MODEL_ORDER}
    meaningful = {m: manifest["models"][m]["meaningful_scores"] for m in MODEL_ORDER}
    metrics = pd.DataFrame(metrics_table(pred, thresholds, meaningful, MODEL_ORDER))
    metrics.to_csv(run / "metrics.csv", index=False, lineterminator="\n")

    plots = run / "plots"
    plots.mkdir(exist_ok=True)
    _plot_confusion(pred, manifest, plots / "confusion_matrices.png")
    _plot_pr(pred, manifest, plots / "precision_recall.png")

    label = LABELS.get("unsw" if manifest["dataset_label"].startswith("unsw") else "synthetic")
    cols = ["model", "threshold", "tp", "fp", "tn", "fn", "accuracy", "precision", "recall", "f1", "fpr", "average_precision"]
    main = metrics[metrics["subset"] == "all"]
    dedup = metrics[metrics["subset"] == "excluding_train_duplicates"]
    iso = main[main["model"] == "isolation_forest"].iloc[0]
    hyb = main[main["model"] == "hybrid_iso_rule"].iloc[0]

    latency_path = run / "latency.json"
    latency = json.loads(latency_path.read_text(encoding="utf-8")) if latency_path.exists() else None
    lat_lines = ""
    if latency:
        hw = latency["hardware"]
        lat_lines = (
            f"Hardware: {hw['system']}, {hw['processor']}, {hw['cpu_count']} logical CPUs, Python {hw['python']}. "
            f"Batch {latency['batch_size']} rows, {latency['models']['mlp']['warmup']} warm-up, "
            f"{latency['models']['mlp']['repeats']} timed repetitions; milliseconds per batch.\n\n"
            "| stage | p50 ms | p95 ms |\n|---|---|---|\n"
            f"| preprocessing | {_fmt(latency['preprocessing']['p50_ms'])} | {_fmt(latency['preprocessing']['p95_ms'])} |\n"
            + "".join(f"| {m} | {_fmt(v['p50_ms'])} | {_fmt(v['p95_ms'])} |\n" for m, v in latency["models"].items())
        )

    ov, q = manifest["duplicate_overlap"], manifest["analyst_queue"]
    inputs = manifest["inputs"]
    text = f"""# Run report: {manifest['run_id']}

**Data label:** {label}

Positive class: {manifest['positive_class']}. Seed {manifest['seed']}. Model version `{manifest['model_version']}`,
source revision `{manifest['source_revision']}`. Every number below is regenerated from `predictions.csv` and
`manifest.json` in this directory by `python -m infra_ids report --run <dir>`.

## Inputs

| partition | file | SHA-256 | rows | label 0 | label 1 |
|---|---|---|---|---|---|
| train | {inputs['train']['filename']} | `{inputs['train']['sha256'][:16]}...` | {inputs['train']['rows_kept']:,} | {inputs['train']['class_distribution']['label_0']:,} | {inputs['train']['class_distribution']['label_1']:,} |
| test | {inputs['test']['filename']} | `{inputs['test']['sha256'][:16]}...` | {inputs['test']['rows_kept']:,} | {inputs['test']['class_distribution']['label_0']:,} | {inputs['test']['class_distribution']['label_1']:,} |

Full hashes, ignored columns and the split are in `manifest.json`. Thresholds and preprocessing used the
fit/validation rows of the training file only ({manifest['split']['sizes']['fit']:,} fit, {manifest['split']['sizes']['validation']:,} validation).

## Held-out results (all test rows, n={len(pred):,}, prevalence {_fmt(float(pred['y_true'].mean()))})

{_table(main, cols)}

Thresholds: {manifest['threshold_rule']}. `average_precision` is `n/a` for the majority and rule references
(constant or binary scores). Plots: `plots/confusion_matrices.png`, `plots/precision_recall.png`.

## Effect of adding the rule to the Isolation Forest (same records, same detector)

| | Isolation Forest | + rule (hybrid) |
|---|---|---|
| recall | {_fmt(iso['recall'])} | {_fmt(hyb['recall'])} |
| precision | {_fmt(iso['precision'])} | {_fmt(hyb['precision'])} |
| F1 | {_fmt(iso['f1'])} | {_fmt(hyb['f1'])} |
| FPR | {_fmt(iso['fpr'])} | {_fmt(hyb['fpr'])} |
| average precision | {_fmt(iso['average_precision'])} | {_fmt(hyb['average_precision'])} |

## Duplicate sensitivity

{ov['test_rows_with_exact_train_duplicate']:,} of {ov['test_rows']:,} test rows have an exact model-input duplicate in the training file;
{ov['of_which_label_disagrees_with_train']:,} of those disagree with the training label. Metrics excluding those rows:

{_table(dedup, cols) if len(dedup) else 'n/a'}

## Inference latency (wall clock, separate from simulated triage)

{lat_lines or 'not measured'}

## Triage and simulated response

Alerts from `{manifest['alerts']['model']}`: {manifest['alerts']['flagged']:,} flagged, {manifest['alerts']['written']:,} written
(truncated: {manifest['alerts']['truncated']}). The analyst queue is a **simulation** driven by alert content alone (no labels) (policy: {q['policy']}):
{q.get('escalated', 0):,} escalated, {q.get('dismissed', 0):,} dismissed, {q.get('open', 0)} still open. Simulated analyst delay
total {q['simulated_total_delay_s']:,} s is generated, not measured, and is not an incident response time.

## What this run does not establish

Public flow-record accuracy is not a national-security or operational-infrastructure outcome. No claim in the
source article about deployment, interviews or sector impact can be evaluated from this data.
"""
    (run / "report.md").write_text(text, encoding="utf-8")
    from infra_ids.results import write_result_tables

    write_result_tables(run)
    return run / "report.md"
