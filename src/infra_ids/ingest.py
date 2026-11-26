"""CSV import: bounded, validated, with opaque row identifiers and an input manifest entry."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from infra_ids.schema import (
    CATEGORICAL_FEATURES,
    CATEGORY_COLUMN,
    FEATURES,
    ID_COLUMN,
    LABEL_COLUMN,
    SchemaError,
    validate_frame,
)

MAX_BYTES = 256 * 1024 * 1024  # refuse unexpectedly large inputs
ROW_ID_PREFIX = "ev_"


@dataclass(frozen=True)
class Ingested:
    frame: pd.DataFrame  # row_id, features, label, attack_cat (evaluation only)
    manifest: dict


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def opaque_row_id(partition: str, raw_id: object) -> str:
    """Stable, non-reversible-by-eye identifier: same partition+id always maps to the same value."""
    return ROW_ID_PREFIX + hashlib.sha256(f"{partition}|{raw_id}".encode()).hexdigest()[:12]


def _check_path(path: str | Path) -> Path:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise SchemaError([f"input file not found: {path}"])
    if p.suffix.lower() != ".csv":
        raise SchemaError([f"expected a .csv file, got '{p.suffix}'"])
    if p.stat().st_size > MAX_BYTES:
        raise SchemaError([f"{p.name} exceeds the {MAX_BYTES // (1024 * 1024)} MiB input limit"])
    return p


def load_csv(path: str | Path, partition: str) -> Ingested:
    """Read, validate and de-identify one CSV. Duplicate event ids keep the first row and are counted."""
    p = _check_path(path)
    try:
        raw = pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise SchemaError([f"{p.name}: unreadable CSV ({exc.__class__.__name__})"]) from exc
    raw.columns = [str(c).strip() for c in raw.columns]
    frame = validate_frame(raw, source=p.name)

    total = len(frame)
    frame = frame.drop_duplicates(subset=ID_COLUMN, keep="first")
    dropped = total - len(frame)

    frame = frame.assign(row_id=[opaque_row_id(partition, i) for i in frame[ID_COLUMN]])
    if CATEGORY_COLUMN not in frame.columns:
        frame[CATEGORY_COLUMN] = ""
    frame[CATEGORY_COLUMN] = frame[CATEGORY_COLUMN].fillna("").astype(str)
    keep = ["row_id", *FEATURES, LABEL_COLUMN, CATEGORY_COLUMN]
    ignored = sorted(set(raw.columns) - set(keep) - {ID_COLUMN})
    out = frame[keep].reset_index(drop=True)

    manifest = {
        "partition": partition,
        "filename": p.name,
        "sha256": sha256_file(p),
        "bytes": p.stat().st_size,
        "rows_read": total,
        "rows_kept": len(out),
        "duplicate_ids_dropped": dropped,
        "ignored_columns": ignored,
        "class_distribution": {
            "label_0": int((out[LABEL_COLUMN] == 0).sum()),
            "label_1": int((out[LABEL_COLUMN] == 1).sum()),
        },
        "categorical_levels": {c: int(out[c].nunique()) for c in CATEGORICAL_FEATURES},
    }
    return Ingested(frame=out, manifest=manifest)
