"""Reusable preprocessing: fitted on training rows only, applied unchanged elsewhere."""

from __future__ import annotations

import numpy as np
import pandas as pd

from infra_ids.schema import CATEGORICAL_FEATURES, NUMERIC_FEATURES, assert_no_leakage

OTHER = "__other__"
Z_CLIP = 10.0


def _signed_log1p(x: np.ndarray) -> np.ndarray:
    return np.sign(x) * np.log1p(np.abs(x))


class Preprocessor:
    """signed log1p -> standardise (train mean/std, clipped) for numerics; top-K one-hot for categoricals."""

    def __init__(self, max_categories: int = 20):
        self.max_categories = max_categories
        self.fitted = False

    def fit(self, df: pd.DataFrame) -> Preprocessor:
        assert_no_leakage(NUMERIC_FEATURES + CATEGORICAL_FEATURES)
        logged = _signed_log1p(df[list(NUMERIC_FEATURES)].to_numpy(dtype=float))
        self.mean_ = logged.mean(axis=0)
        std = logged.std(axis=0)
        self.std_ = np.where(std > 0, std, 1.0)
        self.levels_ = {
            c: list(df[c].value_counts().index[: self.max_categories]) for c in CATEGORICAL_FEATURES
        }
        self.feature_names_ = list(NUMERIC_FEATURES) + [
            f"{c}={lvl}" for c in CATEGORICAL_FEATURES for lvl in [*self.levels_[c], OTHER]
        ]
        self.fitted = True
        return self

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        if not self.fitted:
            raise RuntimeError("Preprocessor must be fitted on training rows before transform")
        logged = _signed_log1p(df[list(NUMERIC_FEATURES)].to_numpy(dtype=float))
        z = np.clip((logged - self.mean_) / self.std_, -Z_CLIP, Z_CLIP)
        blocks = [z]
        for c in CATEGORICAL_FEATURES:
            known = self.levels_[c]
            values = df[c].where(df[c].isin(known), OTHER).to_numpy()
            blocks.append(
                np.stack([(values == lvl).astype(float) for lvl in [*known, OTHER]], axis=1)
            )
        return np.concatenate(blocks, axis=1)

    def fit_transform(self, df: pd.DataFrame) -> np.ndarray:
        return self.fit(df).transform(df)

    def describe(self) -> dict:
        return {
            "numeric": "signed log1p, then standardise with training mean/std, clipped to +/-10",
            "categorical": f"one-hot of the {self.max_categories} most frequent training levels plus '{OTHER}'",
            "n_features_out": len(self.feature_names_),
            "fit_on": "training rows only",
        }
