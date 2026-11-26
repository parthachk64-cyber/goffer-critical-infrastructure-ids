"""Local analyst queue with auditable, append-only disposition history.

open -> reviewed -> dismissed | escalated. Nothing here touches operational infrastructure:
"escalated" is a label in a local file, not an action taken anywhere.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

OPEN, REVIEWED, DISMISSED, ESCALATED = "open", "reviewed", "dismissed", "escalated"
ALLOWED: dict[str, set[str]] = {
    OPEN: {REVIEWED},
    REVIEWED: {DISMISSED, ESCALATED},
    DISMISSED: set(),
    ESCALATED: set(),
}


class InvalidTransition(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC)


class AnalystQueue:
    def __init__(self, path: Path, clock: Callable[[], datetime] = utc_now):
        self.path = Path(path)
        self.clock = clock
        self._history: dict[str, list[dict]] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self._history.setdefault(rec["event_id"], []).append(rec)

    def _append(self, rec: dict) -> dict:
        self._history.setdefault(rec["event_id"], []).append(rec)
        with self.path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
        return rec

    def enqueue(self, alert: dict) -> bool:
        """Add an alert as 'open'. A repeat of a known event id changes nothing and returns False."""
        eid = alert["event_id"]
        if eid in self._history:
            return False
        self._append(
            {"event_id": eid, "from": None, "to": OPEN, "at": self.clock().isoformat(),
             "reason": "alert raised: " + ",".join(alert["reason_codes"]), "actor": "detector",
             "risk_score": alert["risk_score"]}
        )  # fmt: skip
        return True

    def state(self, event_id: str) -> str | None:
        hist = self._history.get(event_id)
        return hist[-1]["to"] if hist else None

    def history(self, event_id: str) -> list[dict]:
        return list(self._history.get(event_id, []))

    def transition(self, event_id: str, to: str, reason: str, actor: str) -> dict:
        current = self.state(event_id)
        if current is None:
            raise InvalidTransition(f"unknown event {event_id}")
        if to not in ALLOWED[current]:
            raise InvalidTransition(f"{event_id}: {current} -> {to} is not allowed")
        if not reason.strip():
            raise InvalidTransition("a reason is required for every transition")
        return self._append(
            {"event_id": event_id, "from": current, "to": to, "at": self.clock().isoformat(),
             "reason": reason, "actor": actor}
        )  # fmt: skip

    def counts(self) -> dict[str, int]:
        out = {s: 0 for s in ALLOWED}
        for hist in self._history.values():
            out[hist[-1]["to"]] += 1
        return out


class SimClock:
    """Deterministic simulated clock for the demo policy; it is not a measurement of any real delay."""

    def __init__(self, start: datetime, seed: int, max_step_s: int = 600):
        self.now = start
        self.rng = np.random.default_rng(seed)
        self.max_step_s = max_step_s
        self.total_simulated_s = 0

    def __call__(self) -> datetime:
        step = int(self.rng.integers(1, self.max_step_s))
        self.now += timedelta(seconds=step)
        self.total_simulated_s += step
        return self.now


def apply_demo_policy(queue: AnalystQueue, alerts: list[dict]) -> dict:
    """Simulated analyst: review every alert; escalate when the alert carries a rule reason code, else dismiss.

    The policy uses only the alert's own content. It never sees ground-truth labels.
    """
    new = 0
    for a in alerts:
        if queue.enqueue(a):
            new += 1
            queue.transition(a["event_id"], REVIEWED, "simulated review", "demo-policy")
            if a["proposed_action"] == "expedite_analyst_review":
                queue.transition(a["event_id"], ESCALATED, "simulated: rule reason code present", "demo-policy")
            else:
                queue.transition(a["event_id"], DISMISSED, "simulated: score-only alert", "demo-policy")
    return {"new_alerts": new, "duplicates_ignored": len(alerts) - new, **queue.counts()}
