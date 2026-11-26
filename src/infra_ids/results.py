"""Public result tables: derive them from a saved run, render them between markers, and check they are current.

Table A  counts of marked cells in the authors' energy case matrix (paper Table 1), from data/paper/energy_case_matrix.csv
Table B  six detectors on the same held-out records (precision, recall, F1, false-positive rate)
Table C  confusion counts, false alerts per 1,000 benign records, inference timing, and the hybrid-vs-detector pairing

Everything is a pure function of files saved in the run directory (or committed data), so re-rendering from the same
inputs is byte-identical. Nothing here invents a number: a missing input is rendered as an explicit status.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

import pandas as pd

from infra_ids.train import MODEL_ORDER

NAMES = {
    "majority_reference": "majority reference",
    "rule_baseline": "rule baseline",
    "decision_tree": "decision tree",
    "isolation_forest": "isolation forest",
    "mlp": "MLP",
    "hybrid_iso_rule": "isolation forest + rule",
}
UNDERLYING, HYBRID = "isolation_forest", "hybrid_iso_rule"
CASES = ("colonial_pipeline_2021", "ukraine_power_grid_2015_2016", "triton_2017", "blackenergy_2014")
CODES = {"marked": "a printed check mark", "not_marked": "a printed cross", "": "illegible or unspecified"}
TABLE_B_FIELDS = ["model", "test_n", "positives", "tp", "fp", "tn", "fn", "accuracy", "precision", "recall", "f1", "fpr",
                  "threshold", "run_id", "dataset_label"]  # fmt: skip
BLOCK = "<!-- BEGIN GENERATED:{name} -->\n{body}\n<!-- END GENERATED:{name} -->"
BLOCK_RE = r"<!-- BEGIN GENERATED:{name} -->\n.*?\n<!-- END GENERATED:{name} -->"


def _f(v, nd: int = 3) -> str:
    if v is None or v == "" or (isinstance(v, float) and v != v):
        return "n/a"
    return f"{float(v):.{nd}f}"


def _csv_text(fields: list[str], rows: list[dict]) -> str:
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


# ---------------------------------------------------------------------------------------------- Table A


def energy_counts(matrix_csv: str | Path) -> list[dict]:
    """Per feature: marked cells / cells examined. An empty cell is unspecified: it is neither marked nor examined."""
    out = []
    with open(matrix_csv, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            codes = [(c, row[c].strip()) for c in CASES]
            bad = [v for _, v in codes if v not in CODES]
            if bad:
                raise ValueError(f"{row['feature']}: unknown cell code {bad}; allowed {sorted(CODES)}")
            out.append({
                "feature": row["feature"],
                "case_columns_marked": sum(v == "marked" for _, v in codes),
                "case_columns_examined": sum(v != "" for _, v in codes),
                "unspecified_cells": sum(v == "" for _, v in codes),
                "marked_cases": ";".join(c for c, v in codes if v == "marked"),
                "source_locator": "Table 1, printed p. 1673",
                "evidence_label": "paper reports (count derived by this repository)",
            })  # fmt: skip
    return out


COUNT_FIELDS = ["feature", "case_columns_marked", "case_columns_examined", "unspecified_cells", "marked_cases",
                "source_locator", "evidence_label"]  # fmt: skip
TABLE_A_FEATURES = ("Phishing", "Ransomware deployment", "SCADA exploitation")


def energy_counts_csv(matrix_csv: str | Path) -> str:
    return _csv_text(COUNT_FIELDS, energy_counts(matrix_csv))


def render_table_a(matrix_csv: str | Path) -> str:
    rows = {r["feature"]: r for r in energy_counts(matrix_csv)}
    lines = ["**Table A. What the paper records in its four energy cases**", "",
             "| Feature marked by the authors | Case columns marked | Case columns examined |", "|---|---|---|"]  # fmt: skip
    for feat in TABLE_A_FEATURES:
        r = rows[feat]
        lines.append(f"| {feat} | {r['case_columns_marked']} | {r['case_columns_examined']} |")
    lines += ["", "*Counts derived from the authors' case matrix* (paper Table 1, printed p. 1673; columns: Colonial Pipeline 2021, "
              "Ukraine power grid 2015/2016 as one column, Triton 2017, BlackEnergy 2014). Each count describes how the authors coded "
              "four selected cases; it cannot estimate how often a threat occurs across the energy sector and is not independent "
              "incident verification. All nine features: [data/paper/energy_case_counts.csv](data/paper/energy_case_counts.csv)."]  # fmt: skip
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------- Tables B and C


def _confusion(y, p) -> tuple[int, int, int, int]:
    tp = int(((y == 1) & (p == 1)).sum())
    fp = int(((y == 0) & (p == 1)).sum())
    tn = int(((y == 0) & (p == 0)).sum())
    fn = int(((y == 1) & (p == 0)).sum())
    return tp, fp, tn, fn


def _ratio(a: int, b: int):
    return a / b if b else None


def table_b_rows(pred: pd.DataFrame, manifest: dict) -> list[dict]:
    y = pred["y_true"].to_numpy()
    rows = []
    for m in MODEL_ORDER:
        tp, fp, tn, fn = _confusion(y, pred[f"pred_{m}"].to_numpy())
        rows.append({
            "model": m, "test_n": len(pred), "positives": int(y.sum()), "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "accuracy": _ratio(tp + tn, len(pred)), "precision": _ratio(tp, tp + fp), "recall": _ratio(tp, tp + fn),
            "f1": _ratio(2 * tp, 2 * tp + fp + fn), "fpr": _ratio(fp, fp + tn),
            "threshold": manifest["models"][m]["threshold"], "run_id": manifest["run_id"],
            "dataset_label": manifest["dataset_label"],
        })  # fmt: skip
    return rows


def table_c_rows(brows: list[dict], latency: dict | None) -> list[dict]:
    rows = []
    for r in brows:
        benign = r["fp"] + r["tn"]
        row = {"model": r["model"], "tp": r["tp"], "fp": r["fp"], "tn": r["tn"], "fn": r["fn"], "benign_records": benign,
               "false_alerts_per_1000_benign": _ratio(1000 * r["fp"], benign), "batch_size": "", "timing_unit": "",
               "p50_ms": "", "p95_ms": "", "timing_samples_saved": "", "timing_status": ""}  # fmt: skip
        if latency is None:
            row["timing_status"] = "not measured: latency.json absent from this run"
        else:
            t = latency["models"].get(r["model"])
            if not t or t.get("p50_ms") is None:
                row["timing_status"] = "unavailable: timing failed or was not recorded for this model"
            else:
                row.update({"batch_size": latency["batch_size"], "timing_unit": "milliseconds per batch (wall clock)",
                            "p50_ms": t["p50_ms"], "p95_ms": t["p95_ms"],
                            "timing_samples_saved": "yes" if t.get("samples_ms") else "no",
                            "timing_status": "measured" if t.get("samples_ms") else "measured; raw samples not saved (run predates sample logging)"})  # fmt: skip
        rows.append(row)
    return rows


def paired_row(pred: pd.DataFrame, manifest: dict) -> dict:
    """Hybrid vs the detector it is built on, on identical records: detections gained and lost, false alerts gained and lost."""
    y = pred["y_true"].to_numpy()
    a, b = pred[f"pred_{UNDERLYING}"].to_numpy(), pred[f"pred_{HYBRID}"].to_numpy()
    gained_tp, lost_tp = int(((y == 1) & (b == 1) & (a == 0)).sum()), int(((y == 1) & (b == 0) & (a == 1)).sum())
    gained_fp, lost_fp = int(((y == 0) & (b == 1) & (a == 0)).sum()), int(((y == 0) & (b == 0) & (a == 1)).sum())
    return {"underlying": UNDERLYING, "hybrid": HYBRID, "test_n": len(pred),
            "underlying_threshold": manifest["models"][UNDERLYING]["threshold"],
            "hybrid_threshold": manifest["models"][HYBRID]["threshold"],
            "gained_true_detections": gained_tp, "lost_true_detections": lost_tp, "net_extra_true_detections": gained_tp - lost_tp,
            "gained_false_alerts": gained_fp, "lost_false_alerts": lost_fp, "net_extra_false_alerts": gained_fp - lost_fp,
            "run_id": manifest["run_id"]}  # fmt: skip


TABLE_C_FIELDS = ["model", "tp", "fp", "tn", "fn", "benign_records", "false_alerts_per_1000_benign", "batch_size", "timing_unit",
                  "p50_ms", "p95_ms", "timing_samples_saved", "timing_status"]  # fmt: skip
PAIRED_FIELDS = ["underlying", "hybrid", "test_n", "underlying_threshold", "hybrid_threshold", "gained_true_detections",
                 "lost_true_detections", "net_extra_true_detections", "gained_false_alerts", "lost_false_alerts",
                 "net_extra_false_alerts", "run_id"]  # fmt: skip


def derived_texts(run: Path) -> dict[str, str]:
    """The three CSVs as text, derived from predictions.csv + manifest.json + latency.json."""
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    pred = pd.read_csv(run / "predictions.csv")
    lp = run / "latency.json"
    latency = json.loads(lp.read_text(encoding="utf-8")) if lp.exists() else None
    b = table_b_rows(pred, manifest)
    return {
        "table_b.csv": _csv_text(TABLE_B_FIELDS, b),
        "table_c.csv": _csv_text(TABLE_C_FIELDS, table_c_rows(b, latency)),
        "paired.csv": _csv_text(PAIRED_FIELDS, [paired_row(pred, manifest)]),
    }


def write_result_tables(run: str | Path) -> list[Path]:
    run = Path(run)
    out = []
    for name, text in derived_texts(run).items():
        (run / name).write_text(text, encoding="utf-8", newline="\n")
        out.append(run / name)
    return out


def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _title(manifest: dict) -> str:
    if manifest["dataset_label"].startswith("unsw"):
        return "UNSW-NB15 official training/testing partitions (independent benchmark)"
    return "Synthetic demo results (seeded generator, not real traffic; the UNSW-NB15 comparison is pending)"


def render_table_b(run: Path, run_rel: str) -> str:
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    rows = _read_csv(run / "table_b.csv")
    heading = "Synthetic demo results" if not manifest["dataset_label"].startswith("unsw") else "Detectors on the UNSW-NB15 test partition"
    n = rows[0]["test_n"]
    lines = [f"**Table B. How the six detectors performed on the same held-out records: {heading}**", "",
             "| Model | Test N | Precision | Recall | F1 | False-positive rate |", "|---|---|---|---|---|---|"]  # fmt: skip
    for r in rows:
        lines.append(f"| {NAMES[r['model']]} | {int(r['test_n']):,} | {_f(r['precision'] or None)} | {_f(r['recall'] or None)} | "
                     f"{_f(r['f1'] or None)} | {_f(r['fpr'] or None)} |")  # fmt: skip
    pos = int(rows[0]["positives"])
    lines += ["", f"*Dataset: {_title(manifest)}. Split: provider's held-out test file, n={int(n):,} ({pos:,} attack, "
              f"{int(n) - pos:,} normal). Positive class: label 1 (attack). Thresholds: each detector's own, chosen to maximise F1 on a "
              f"validation split of the training file (reference models use a fixed 0.5). Run ID: `{manifest['run_id']}`, seed "
              f"{manifest['seed']}, source revision `{manifest['source_revision'][:10]}`.* "
              f"Undefined ratios are `n/a`. Download: [{run_rel}/table_b.csv]({run_rel}/table_b.csv) (adds accuracy and confusion counts). "
              f"Errors and timing: [docs/results.md](docs/results.md)."]  # fmt: skip
    return "\n".join(lines)


def render_table_c(run: Path, run_rel: str) -> str:
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    rows = _read_csv(run / "table_c.csv")
    lines = [f"**Table C. Errors and inference time: {_title(manifest)}, run `{manifest['run_id']}`**", "",
             "| Model | TP | FP | TN | FN | False alerts per 1,000 benign | p50 (ms/batch) | p95 (ms/batch) | Batch | Timing status |",
             "|---|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
    for r in rows:
        fa = _f(r["false_alerts_per_1000_benign"] or None, 1)
        lines.append(f"| {NAMES[r['model']]} | {int(r['tp']):,} | {int(r['fp']):,} | {int(r['tn']):,} | {int(r['fn']):,} | {fa} | "
                     f"{_f(r['p50_ms'] or None, 2)} | {_f(r['p95_ms'] or None, 2)} | {r['batch_size'] or 'n/a'} | {r['timing_status']} |")  # fmt: skip
    p = _read_csv(run / "paired.csv")[0]
    lines += ["", f"*Denominators: benign records = FP + TN = {int(rows[0]['benign_records']):,}; test N = {int(p['test_n']):,}. "
              "Timing is wall-clock inference on one batch (milliseconds per batch, unit as in the column headers), measured "
              "separately from any simulated triage delay; hardware and warm-up/repeat counts are in the run's `latency.json` "
              f"and report. CSVs: [{run_rel}/table_c.csv]({run_rel}/table_c.csv).*", "",
              "**Hybrid versus its underlying detector (same records)**", "",
              "| | Isolation forest | Isolation forest + rule | Gained by the rule | Lost by the rule | Net |", "|---|---|---|---|---|---|"]  # fmt: skip
    by = {r["model"]: r for r in _read_csv(run / "table_b.csv")}
    iso, hyb = by[UNDERLYING], by[HYBRID]
    lines += [f"| true detections (TP) | {int(iso['tp']):,} | {int(hyb['tp']):,} | {int(p['gained_true_detections']):,} | "
              f"{int(p['lost_true_detections']):,} | {int(p['net_extra_true_detections']):+,} |",
              f"| false alerts (FP) | {int(iso['fp']):,} | {int(hyb['fp']):,} | {int(p['gained_false_alerts']):,} | "
              f"{int(p['lost_false_alerts']):,} | {int(p['net_extra_false_alerts']):+,} |", "",
              f"*At the selected operating points (isolation forest threshold {_f(p['underlying_threshold'])}, hybrid threshold "
              f"{_f(p['hybrid_threshold'])}). The rule is one documented choice, so this is a measurement for that choice, not for hybrids in general.*"]  # fmt: skip
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------- README / docs updating


def _replace_block(text: str, name: str, body: str) -> str:
    pat = re.compile(BLOCK_RE.format(name=re.escape(name)), re.S)
    if not pat.search(text):
        raise ValueError(f"marker pair for '{name}' not found; add {BLOCK.format(name=name, body='...')} where it belongs")
    return pat.sub(lambda _m: BLOCK.format(name=name, body=body), text, count=1)


def expected_documents(run: Path, run_rel: str, readme_text: str, results_text: str, matrix_csv: Path) -> tuple[str, str]:
    new_readme = _replace_block(readme_text, "table-a", render_table_a(matrix_csv))
    new_readme = _replace_block(new_readme, "table-b", render_table_b(run, run_rel))
    new_results = _replace_block(results_text, "table-c", render_table_c(run, run_rel))
    return new_readme, new_results


def update_or_check(run: Path, readme: Path, results_md: Path, matrix_csv: Path, counts_csv: Path, check: bool,
                    run_rel: str | None = None) -> list[str]:
    """Return a list of problems. In check mode nothing is written. Otherwise generated sections and CSVs are rewritten."""
    problems: list[str] = []
    run_rel = run_rel or run.as_posix()
    have_pred = (run / "predictions.csv").exists()
    if have_pred:
        derived = derived_texts(run)
        for name, text in derived.items():
            f = run / name
            if check and (not f.exists() or f.read_text(encoding="utf-8") != text):
                problems.append(f"{f} is stale or missing: re-run `report --run {run_rel}`")
    elif check:
        for name in ("table_b.csv", "table_c.csv", "paired.csv"):
            if not (run / name).exists():
                problems.append(f"{run / name} is missing and predictions.csv is absent, so it cannot be re-derived")
        problems += _metrics_consistency(run)
    if problems and check:
        return problems
    counts_text = energy_counts_csv(matrix_csv)
    if check:
        if not counts_csv.exists() or counts_csv.read_text(encoding="utf-8") != counts_text:
            problems.append(f"{counts_csv} is stale: regenerate with `report --run {run_rel} --update-readme`")
    else:
        counts_csv.write_text(counts_text, encoding="utf-8", newline="\n")
        if have_pred:
            write_result_tables(run)
    r_text, d_text = readme.read_text(encoding="utf-8"), results_md.read_text(encoding="utf-8")
    new_r, new_d = expected_documents(run, run_rel, r_text, d_text, matrix_csv)
    if check:
        if new_r != r_text:
            problems.append(f"{readme} has a stale generated section (table-a or table-b)")
        if new_d != d_text:
            problems.append(f"{results_md} has a stale generated section (table-c)")
    else:
        readme.write_text(new_r, encoding="utf-8", newline="\n")
        results_md.write_text(new_d, encoding="utf-8", newline="\n")
    return problems


def _metrics_consistency(run: Path) -> list[str]:
    """Without predictions: the committed table_b.csv must agree with the committed metrics.csv counts."""
    out = []
    mp, bp = run / "metrics.csv", run / "table_b.csv"
    if not (mp.exists() and bp.exists()):
        return out
    m = {r["model"]: r for r in _read_csv(mp) if r["subset"] == "all"}
    for r in _read_csv(bp):
        ref = m.get(r["model"])
        if ref is None or any(int(float(ref[k])) != int(r[k]) for k in ("tp", "fp", "tn", "fn")):
            out.append(f"{bp}: counts for {r['model']} disagree with metrics.csv")
        if int(r["tp"]) + int(r["fp"]) + int(r["tn"]) + int(r["fn"]) != int(r["test_n"]):
            out.append(f"{bp}: {r['model']} confusion counts do not sum to test N")
    return out
