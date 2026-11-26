"""Turn scored records into local alerts: event id, model version, score, threshold, reason codes, action."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import numpy as np

RULE_CODE_PREFIX = "R"  # rule reason codes: R1_..., R2_...
ACTION_EXPEDITE = "expedite_analyst_review"
ACTION_REVIEW = "analyst_review"


def propose_action(codes: list[str]) -> str:
    """Expedite when a documented rule also fired; otherwise ordinary analyst review."""
    return ACTION_EXPEDITE if any(c.startswith(RULE_CODE_PREFIX) for c in codes) else ACTION_REVIEW


def build_alerts(
    row_ids,
    scores,
    threshold: float,
    model_name: str,
    model_version: str,
    reasons_fn: Callable[[int], list[str]],
    max_alerts: int | None = None,
) -> tuple[list[dict], dict]:
    """Alerts for rows with score >= threshold, highest risk first. Reports truncation explicitly."""
    s = np.asarray(scores, dtype=float)
    flagged = np.flatnonzero(s >= threshold)
    order = flagged[np.argsort(-s[flagged], kind="stable")]
    truncated = max_alerts is not None and len(order) > max_alerts
    if truncated:
        order = order[:max_alerts]
    alerts = []
    for i in order:
        codes = ["SCORE_ABOVE_THRESHOLD", *reasons_fn(int(i))]
        alerts.append(
            {
                "event_id": str(row_ids[i]),
                "model": model_name,
                "model_version": model_version,
                "risk_score": round(float(s[i]), 6),
                "threshold": round(float(threshold), 6),
                "reason_codes": codes,
                "proposed_action": propose_action(codes),
            }
        )
    return alerts, {"flagged": int(len(flagged)), "written": len(alerts), "truncated": bool(truncated)}


def write_alerts(path: Path, alerts: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for a in alerts:
            fh.write(json.dumps(a, sort_keys=True) + "\n")


def read_alerts(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
