"""Detectors. Every detector returns a score in [0, 1]; higher means more suspicious.

Model choices here (tree depth, MLP size, the rule, the fusion formula) are decisions of this
repository. The source article names model families but gives no configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neural_network import MLPClassifier
from sklearn.tree import DecisionTreeClassifier

# Rule clauses, fixed a priori from the documented semantics of the ct_* and packet-count fields.
# They are not tuned on any test partition.
RULE_FANIN_MIN = 8  # >= 8 of the last 100 connections hit the same service and destination
RULE_UNANSWERED_MIN_SPKTS = 2  # at least two packets sent and nothing returned
HYBRID_RULE_WEIGHT = 0.5  # how far a rule hit lifts the detector score toward 1


def rule_reasons(raw: pd.DataFrame) -> list[list[str]]:
    """Per-row list of matched rule clause codes."""
    fanin = ((raw["ct_srv_dst"] >= RULE_FANIN_MIN) & (raw["ct_dst_ltm"] >= RULE_FANIN_MIN)).to_numpy()
    unanswered = ((raw["dpkts"] == 0) & (raw["spkts"] >= RULE_UNANSWERED_MIN_SPKTS)).to_numpy()
    return [
        [code for code, hit in (("R1_FANIN_BURST", f), ("R2_UNANSWERED", u)) if hit]
        for f, u in zip(fanin, unanswered, strict=True)
    ]


def rule_flags(raw: pd.DataFrame) -> np.ndarray:
    return np.array([1.0 if r else 0.0 for r in rule_reasons(raw)])


@dataclass
class MajorityReference:
    """Predicts the majority training label for every record. Constant score."""

    name: str = "majority_reference"
    meaningful_scores: bool = False
    majority_: float = field(default=0.0, init=False)

    def fit(self, X, y, raw):
        self.majority_ = 1.0 if float(np.mean(y)) >= 0.5 else 0.0
        return self

    def score(self, X, raw):
        return np.full(len(X), self.majority_)

    def config(self):
        return {"rule": "predict the majority class of the fit rows"}


@dataclass
class RuleBaseline:
    """R1 fan-in burst OR R2 unanswered probe. Binary score."""

    name: str = "rule_baseline"
    meaningful_scores: bool = False

    def fit(self, X, y, raw):
        return self

    def score(self, X, raw):
        return rule_flags(raw)

    def config(self):
        return {
            "R1_FANIN_BURST": f"ct_srv_dst >= {RULE_FANIN_MIN} and ct_dst_ltm >= {RULE_FANIN_MIN}",
            "R2_UNANSWERED": f"dpkts == 0 and spkts >= {RULE_UNANSWERED_MIN_SPKTS}",
            "decision": "R1 or R2",
        }


@dataclass
class DecisionTree:
    seed: int
    name: str = "decision_tree"
    meaningful_scores: bool = True
    max_depth: int = 8
    min_samples_leaf: int = 20

    def fit(self, X, y, raw):
        self.model_ = DecisionTreeClassifier(
            max_depth=self.max_depth, min_samples_leaf=self.min_samples_leaf, random_state=self.seed
        ).fit(X, y)
        return self

    def score(self, X, raw):
        proba = self.model_.predict_proba(X)
        return proba[:, list(self.model_.classes_).index(1)] if 1 in self.model_.classes_ else np.zeros(len(X))

    def config(self):
        return {"max_depth": self.max_depth, "min_samples_leaf": self.min_samples_leaf, "seed": self.seed}


@dataclass
class IsolationDetector:
    """Isolation Forest fitted on normal (label 0) fit rows only.

    Raw anomaly = -score_samples (higher = more anomalous). Normalisation: empirical CDF against
    the fit-row normal scores, so a score is the share of normal training records scoring lower.
    """

    seed: int
    name: str = "isolation_forest"
    meaningful_scores: bool = True
    n_estimators: int = 200

    def fit(self, X, y, raw):
        normal = X[np.asarray(y) == 0]
        if len(normal) == 0:
            raise ValueError("Isolation Forest needs normal training records")
        self.model_ = IsolationForest(
            n_estimators=self.n_estimators, random_state=self.seed, n_jobs=1
        ).fit(normal)
        self.ref_ = np.sort(-self.model_.score_samples(normal))
        return self

    def score(self, X, raw):
        anomaly = -self.model_.score_samples(X)
        return np.searchsorted(self.ref_, anomaly, side="right") / len(self.ref_)

    def config(self):
        return {"n_estimators": self.n_estimators, "fit_on": "label 0 fit rows only", "seed": self.seed,
                "normalisation": "empirical CDF over fit-row normal scores"}


@dataclass
class MLPDetector:
    seed: int
    name: str = "mlp"
    meaningful_scores: bool = True
    hidden: tuple[int, ...] = (32, 16)

    def fit(self, X, y, raw):
        self.model_ = MLPClassifier(
            hidden_layer_sizes=self.hidden, early_stopping=True, max_iter=200,
            random_state=self.seed,
        ).fit(X, y)
        return self

    def score(self, X, raw):
        return self.model_.predict_proba(X)[:, list(self.model_.classes_).index(1)]

    def config(self):
        return {"hidden_layer_sizes": list(self.hidden), "early_stopping": True, "max_iter": 200, "seed": self.seed}


@dataclass
class HybridIsolationRule:
    """s = 1 - (1 - s_iso) * (1 - w * r): a rule hit lifts the anomaly score; no hit leaves it unchanged."""

    base: IsolationDetector
    name: str = "hybrid_iso_rule"
    meaningful_scores: bool = True
    weight: float = HYBRID_RULE_WEIGHT

    def fit(self, X, y, raw):
        return self  # base is fitted separately and shared, so the comparison is like for like

    def combine(self, base_scores, raw):
        return 1.0 - (1.0 - base_scores) * (1.0 - self.weight * rule_flags(raw))

    def score(self, X, raw):
        return self.combine(self.base.score(X, raw), raw)

    def config(self):
        return {"formula": "1 - (1 - s_iso) * (1 - w * r)", "w": self.weight, "rule": "R1 or R2"}
