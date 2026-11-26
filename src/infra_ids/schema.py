"""Flow-record schema: the model-input allowlist, forbidden outcome fields, and validation.

The allowlist is the only source of model inputs. Anything not listed (target, attack category,
row identifiers, raw TCP sequence numbers, unknown extras) is excluded by construction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Numeric flow features shared by the UNSW-NB15 partition CSVs and the synthetic fixture.
NUMERIC_FEATURES: tuple[str, ...] = (
    "dur", "spkts", "dpkts", "sbytes", "dbytes", "rate", "sttl", "dttl", "sload", "dload",
    "sloss", "dloss", "sinpkt", "dinpkt", "sjit", "djit", "swin", "dwin", "tcprtt", "synack",
    "ackdat", "smean", "dmean", "trans_depth", "response_body_len", "ct_srv_src", "ct_state_ttl",
    "ct_dst_ltm", "ct_src_dport_ltm", "ct_dst_sport_ltm", "ct_dst_src_ltm", "is_ftp_login",
    "ct_ftp_cmd", "ct_flw_http_mthd", "ct_src_ltm", "ct_srv_dst", "is_sm_ips_ports",
)  # fmt: skip
CATEGORICAL_FEATURES: tuple[str, ...] = ("proto", "service", "state")
FEATURES: tuple[str, ...] = CATEGORICAL_FEATURES + NUMERIC_FEATURES

ID_COLUMN = "id"
LABEL_COLUMN = "label"
CATEGORY_COLUMN = "attack_cat"  # evaluation only, never a model input

# Outcome-derived or non-semantic fields that must never reach a model.
FORBIDDEN_INPUTS: frozenset[str] = frozenset({LABEL_COLUMN, CATEGORY_COLUMN, ID_COLUMN, "row_id", "stcpb", "dtcpb"})

REQUIRED_COLUMNS: tuple[str, ...] = (ID_COLUMN, LABEL_COLUMN) + FEATURES


class SchemaError(ValueError):
    """Raised with every problem found, so an analyst can fix the file in one pass."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def assert_no_leakage(columns) -> None:
    """Fail if a forbidden field appears among model-input columns."""
    leaked = sorted(set(columns) & FORBIDDEN_INPUTS)
    if leaked:
        raise SchemaError([f"forbidden model-input columns present: {leaked}"])


def validate_frame(df: pd.DataFrame, source: str = "input") -> pd.DataFrame:
    """Validate and normalise a raw frame. Returns a frame with numeric dtypes enforced."""
    problems: list[str] = []
    if df.empty:
        raise SchemaError([f"{source}: file has no rows"])
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise SchemaError([f"{source}: missing required columns {missing}"])

    out = df.copy()
    for col in NUMERIC_FEATURES + (LABEL_COLUMN,):
        coerced = pd.to_numeric(out[col], errors="coerce")
        bad = int(coerced.isna().sum())
        if bad:
            problems.append(f"{source}: column '{col}' has {bad} non-numeric or missing values")
        elif not np.isfinite(coerced.to_numpy(dtype=float)).all():
            problems.append(f"{source}: column '{col}' has infinite values")
        out[col] = coerced
    for col in CATEGORICAL_FEATURES:
        if out[col].isna().any():
            problems.append(f"{source}: column '{col}' has missing values")
        out[col] = out[col].astype(str).str.strip()
    if out[ID_COLUMN].isna().any():
        problems.append(f"{source}: column '{ID_COLUMN}' has missing values")
    if problems:
        raise SchemaError(problems)

    if not out[LABEL_COLUMN].isin([0, 1]).all():
        problems.append(f"{source}: '{LABEL_COLUMN}' must be 0 or 1")
    for col in ("dur", "spkts", "dpkts", "sbytes", "dbytes"):
        if (out[col] < 0).any():
            problems.append(f"{source}: column '{col}' has negative values")
    if problems:
        raise SchemaError(problems)
    out[LABEL_COLUMN] = out[LABEL_COLUMN].astype(int)
    return out
