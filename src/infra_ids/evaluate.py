"""Metrics with explicit handling of undefined denominators, threshold choice, and latency timing."""

from __future__ import annotations

import platform
import time

import numpy as np
from sklearn.metrics import average_precision_score

POSITIVE_CLASS = 1  # label 1 = attack / malicious flow


def _ratio(num: float, den: float) -> float | None:
    return None if den == 0 else num / den


def confusion(y_true, y_pred) -> dict[str, int]:
    y_true = np.asarray(y_true).astype(int)
    y_pred = np.asarray(y_pred).astype(int)
    return {
        "tp": int(((y_true == 1) & (y_pred == 1)).sum()),
        "fp": int(((y_true == 0) & (y_pred == 1)).sum()),
        "tn": int(((y_true == 0) & (y_pred == 0)).sum()),
        "fn": int(((y_true == 1) & (y_pred == 0)).sum()),
    }


def metrics_from_counts(c: dict[str, int]) -> dict[str, float | None]:
    tp, fp, tn, fn = c["tp"], c["fp"], c["tn"], c["fn"]
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    f1 = None if precision is None or recall is None or precision + recall == 0 else 2 * precision * recall / (precision + recall)
    if f1 is None and precision is not None and recall is not None:
        f1 = 0.0
    return {
        "accuracy": _ratio(tp + tn, tp + fp + tn + fn),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fpr": _ratio(fp, fp + tn),
    }


def average_precision(y_true, scores, meaningful: bool) -> float | None:
    """None for constant/binary reference scores or when a class is absent."""
    y = np.asarray(y_true).astype(int)
    if not meaningful or y.min() == y.max():
        return None
    return float(average_precision_score(y, scores))


def select_threshold(y_true, scores, max_candidates: int = 2000) -> float:
    """Threshold maximising F1 on validation data; predict positive iff score >= threshold.

    Ties go to the higher threshold. With no positives, returns a value above every score so nothing is flagged.
    """
    y = np.asarray(y_true).astype(int)
    s = np.asarray(scores, dtype=float)
    if y.sum() == 0:
        return float(s.max()) + 1e-9
    cands = np.unique(s)
    if len(cands) > max_candidates:
        cands = np.unique(np.quantile(s, np.linspace(0, 1, max_candidates)))
    best_t, best_f1 = float(cands[-1]), -1.0
    for t in cands:
        f1 = metrics_from_counts(confusion(y, (s >= t).astype(int)))["f1"] or 0.0
        if f1 >= best_f1:
            best_t, best_f1 = float(t), f1
    return best_t


def metric_row(model: str, y_true, scores, threshold: float, meaningful: bool, subset: str = "all", decisions=None) -> dict:
    """`decisions` are the saved 0/1 decisions made at full score precision. Saved scores are rounded to 6 decimals, so
    re-thresholding them can flip borderline records; when decisions are available they, not a re-threshold, define the counts."""
    y = np.asarray(y_true).astype(int)
    pred = np.asarray(decisions).astype(int) if decisions is not None else (np.asarray(scores) >= threshold).astype(int)
    c = confusion(y, pred)
    return {
        "model": model,
        "subset": subset,
        "n": len(y),
        "positives": int(y.sum()),
        "prevalence": _ratio(int(y.sum()), len(y)),
        "threshold": threshold,
        **c,
        **metrics_from_counts(c),
        "average_precision": average_precision(y, scores, meaningful),
    }


def time_inference(score_fn, batch, warmup: int = 5, repeats: int = 30) -> dict:
    """Wall-clock latency of score_fn(batch) in milliseconds, after warm-up. Excludes any simulated delay."""
    for _ in range(warmup):
        score_fn(batch)
    samples = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        score_fn(batch)
        samples.append((time.perf_counter() - t0) * 1000.0)
    arr = np.asarray(samples)
    return {
        "p50_ms": float(np.percentile(arr, 50)),
        "p95_ms": float(np.percentile(arr, 95)),
        "warmup": warmup,
        "repeats": repeats,
        "samples_ms": [float(x) for x in arr],
    }


def hardware_info() -> dict:
    import os

    return {
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "cpu_count": os.cpu_count(),
        "system": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
    }


def metrics_table(pred, thresholds: dict[str, float], meaningful: dict[str, bool], models) -> list[dict]:
    """Metric rows from a predictions frame: all rows, and rows without an exact training duplicate."""
    rows = []
    subsets = {"all": pred}
    if "train_duplicate" in pred.columns:
        subsets["excluding_train_duplicates"] = pred[pred["train_duplicate"] == 0]
    for subset, frame in subsets.items():
        for m in models:
            rows.append(
                metric_row(m, frame["y_true"], frame[f"score_{m}"], thresholds[m], meaningful[m], subset,
                           frame[f"pred_{m}"] if f"pred_{m}" in frame.columns else None)
            )
    return rows
