"""Fit the preprocessor and all detectors on fit rows; choose thresholds on validation rows only.

No model artifact is pickled: runs are rebuilt deterministically from the seed, so nothing
untrusted is ever deserialised.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from infra_ids import __version__
from infra_ids.detectors import (
    DecisionTree,
    HybridIsolationRule,
    IsolationDetector,
    MajorityReference,
    MLPDetector,
    RuleBaseline,
)
from infra_ids.evaluate import select_threshold
from infra_ids.features import Preprocessor
from infra_ids.schema import LABEL_COLUMN
from infra_ids.splits import validation_split

MODEL_ORDER = (
    "majority_reference", "rule_baseline", "decision_tree", "isolation_forest", "mlp", "hybrid_iso_rule",
)  # fmt: skip
DEVIATION_FLOOR = 3.0  # |z| distance from the normal-record mean that earns a reason code
MAX_DEVIATION_CODES = 3


@dataclass
class Bundle:
    seed: int
    version: str
    pre: Preprocessor
    detectors: dict
    thresholds: dict[str, float]
    normal_mean: np.ndarray
    normal_std: np.ndarray
    fit_n: int
    val_n: int
    val_fraction: float

    def score_all(self, X: np.ndarray, raw: pd.DataFrame) -> dict[str, np.ndarray]:
        out = {n: self.detectors[n].score(X, raw) for n in MODEL_ORDER if n != "hybrid_iso_rule"}
        out["hybrid_iso_rule"] = self.detectors["hybrid_iso_rule"].combine(out["isolation_forest"], raw)  # reuse base scores
        return {n: out[n] for n in MODEL_ORDER}


def train(train_df: pd.DataFrame, seed: int, val_fraction: float = 0.2) -> tuple[Bundle, pd.DataFrame]:
    """Returns (bundle, validation_frame). Preprocessing and thresholds never see the test partition."""
    fit_idx, val_idx = validation_split(train_df, val_fraction, seed)
    fit_df = train_df.iloc[fit_idx].reset_index(drop=True)
    val_df = train_df.iloc[val_idx].reset_index(drop=True)

    pre = Preprocessor().fit(fit_df)
    X_fit, X_val = pre.transform(fit_df), pre.transform(val_df)
    y_fit, y_val = fit_df[LABEL_COLUMN].to_numpy(), val_df[LABEL_COLUMN].to_numpy()

    iso = IsolationDetector(seed=seed)
    detectors = {
        "majority_reference": MajorityReference(),
        "rule_baseline": RuleBaseline(),
        "decision_tree": DecisionTree(seed=seed),
        "isolation_forest": iso,
        "mlp": MLPDetector(seed=seed),
    }
    detectors["hybrid_iso_rule"] = HybridIsolationRule(base=iso)
    for name in ("majority_reference", "rule_baseline", "decision_tree", "isolation_forest", "mlp"):
        detectors[name].fit(X_fit, y_fit, fit_df)

    thresholds = {}
    for name in MODEL_ORDER:
        scores = detectors[name].score(X_val, val_df)
        # Constant/binary reference scores use a fixed 0.5 cut: >= 0.5 means "flag".
        thresholds[name] = 0.5 if name in ("majority_reference", "rule_baseline") else select_threshold(y_val, scores)

    normal = X_fit[y_fit == 0]
    std = normal.std(axis=0)
    bundle = Bundle(
        seed=seed,
        version=f"infra-ids-{__version__}-seed{seed}",
        pre=pre,
        detectors=detectors,
        thresholds=thresholds,
        normal_mean=normal.mean(axis=0),
        normal_std=np.where(std > 1e-6, std, 1.0),
        fit_n=len(fit_df),
        val_n=len(val_df),
        val_fraction=val_fraction,
    )
    return bundle, val_df


def deviation_codes(bundle: Bundle, X_row: np.ndarray) -> list[str]:
    """Feature-name reason codes for numeric features far from the normal-record profile (no values logged)."""
    n_numeric = len(bundle.pre.feature_names_) - sum(len(v) + 1 for v in bundle.pre.levels_.values())
    dev = np.abs((X_row[:n_numeric] - bundle.normal_mean[:n_numeric]) / bundle.normal_std[:n_numeric])
    order = np.argsort(-dev)[:MAX_DEVIATION_CODES]
    return [f"DEV:{bundle.pre.feature_names_[i]}" for i in order if dev[i] >= DEVIATION_FLOOR]
