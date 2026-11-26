"""Validation split inside training, and exact-duplicate inspection across provider partitions."""

from __future__ import annotations

import numpy as np
import pandas as pd

from infra_ids.schema import FEATURES, LABEL_COLUMN, NUMERIC_FEATURES


def feature_hash(df: pd.DataFrame) -> pd.Series:
    """64-bit hash of the model-input columns only (no label, no id)."""
    frame = df[list(FEATURES)].copy()
    frame[list(NUMERIC_FEATURES)] = frame[list(NUMERIC_FEATURES)].astype("float64")  # int 1 and float 1.0 hash alike
    return pd.Series(pd.util.hash_pandas_object(frame, index=False).to_numpy(), index=df.index)


def validation_split(train: pd.DataFrame, val_fraction: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Group-aware split: rows sharing an exact feature vector stay on the same side.

    Returns (train_idx, val_idx) as positional indices. Groups are shuffled with a seeded
    generator and assigned to validation until the requested fraction is reached.
    """
    if not 0 < val_fraction < 1:
        raise ValueError("val_fraction must be between 0 and 1")
    hashes = feature_hash(train).to_numpy()
    groups, inverse = np.unique(hashes, return_inverse=True)
    sizes = np.bincount(inverse)
    order = np.random.default_rng(seed).permutation(len(groups))
    target = val_fraction * len(train)
    in_val = np.zeros(len(groups), dtype=bool)
    taken = 0
    for g in order:
        if taken >= target:
            break
        in_val[g] = True
        taken += sizes[g]
    mask = in_val[inverse]
    return np.flatnonzero(~mask), np.flatnonzero(mask)


def overlap_report(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    """Exact feature-vector overlap between provider partitions, with label agreement."""
    th = feature_hash(train)
    eh = feature_hash(test)
    train_labels = train.assign(_h=th).groupby("_h")[LABEL_COLUMN].agg(["min", "max"])
    in_train = eh.isin(set(th))
    conflicting = 0
    for h, y in zip(eh[in_train], test.loc[in_train, LABEL_COLUMN], strict=True):
        lo, hi = train_labels.loc[h, "min"], train_labels.loc[h, "max"]
        if lo != hi or lo != y:
            conflicting += 1
    return {
        "test_rows": len(test),
        "test_rows_with_exact_train_duplicate": int(in_train.sum()),
        "share_of_test": float(in_train.mean()) if len(test) else None,
        "of_which_label_disagrees_with_train": conflicting,
        "train_rows_internally_duplicated": int(th.duplicated(keep=False).sum()),
    }


def split_manifest(train_n: int, val_n: int, test_n: int, val_fraction: float, seed: int) -> dict:
    return {
        "provider_partitions": "training CSV -> fit/validation; testing CSV -> final evaluation only",
        "validation": "group-aware by exact feature vector, seeded, taken from the training CSV",
        "val_fraction_requested": val_fraction,
        "seed": seed,
        "sizes": {"fit": train_n, "validation": val_n, "test": test_n},
    }
