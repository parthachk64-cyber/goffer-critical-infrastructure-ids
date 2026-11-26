"""Seeded, wholly synthetic flow-record fixture generator (no real traffic, no payloads).

Columns mirror the UNSW-NB15 partition CSVs so the same pipeline runs on both. Four scenarios,
including two deliberately ambiguous ones, keep the task non-trivial. The `scenario` column is
fixture-only documentation; ingest ignores it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from infra_ids.schema import NUMERIC_FEATURES

MIX = {"clean_benign": 0.55, "clean_attack": 0.24, "ambiguous_benign": 0.10, "ambiguous_attack": 0.11}
TRAIN_ROWS, TEST_ROWS = 2000, 1000
FLOAT_FORMAT = "%.6g"


def _block(rng: np.random.Generator, n: int, scenario: str) -> pd.DataFrame:
    p = {
        "clean_benign": dict(spk=8, dpk=10, ctsd=3, ctdl=3, unanswered=0.02, rate=40.0, dur=-3.0),
        "ambiguous_benign": dict(spk=40, dpk=45, ctsd=9, ctdl=9, unanswered=0.05, rate=400.0, dur=-1.5),
        "clean_attack": dict(spk=3, dpk=1, ctsd=14, ctdl=14, unanswered=0.6, rate=900.0, dur=-5.0),
        "ambiguous_attack": dict(spk=9, dpk=8, ctsd=4, ctdl=4, unanswered=0.1, rate=60.0, dur=-2.8),
    }[scenario]
    spkts = rng.poisson(p["spk"], n) + 1
    answered = rng.random(n) >= p["unanswered"]
    dpkts = np.where(answered, rng.poisson(p["dpk"], n) + 1, 0)
    dur = np.exp(rng.normal(p["dur"], 0.9, n))
    sbytes = spkts * rng.lognormal(5.0, 0.6, n)
    dbytes = dpkts * rng.lognormal(5.5, 0.7, n)
    noisy_ct = lambda m: np.clip(rng.poisson(m, n) + rng.integers(0, 4, n), 1, 60)  # noqa: E731
    frame = pd.DataFrame(
        {
            "proto": rng.choice(["tcp", "udp", "icmp"], n, p=[0.7, 0.25, 0.05]),
            "service": rng.choice(["-", "http", "dns", "smtp", "ftp"], n, p=[0.4, 0.3, 0.2, 0.05, 0.05]),
            "state": rng.choice(["FIN", "CON", "INT", "REQ"], n, p=[0.55, 0.2, 0.15, 0.1]),
            "dur": dur,
            "spkts": spkts,
            "dpkts": dpkts,
            "sbytes": sbytes.round(),
            "dbytes": dbytes.round(),
            "rate": p["rate"] * rng.lognormal(0, 0.8, n),
            "sttl": rng.choice([62, 254], n, p=[0.6, 0.4]),
            "dttl": rng.choice([252, 60, 0], n, p=[0.5, 0.4, 0.1]),
            "sload": sbytes * 8 / np.maximum(dur, 1e-3),
            "dload": dbytes * 8 / np.maximum(dur, 1e-3),
            "sloss": rng.poisson(0.3, n),
            "dloss": rng.poisson(0.3, n),
            "sinpkt": dur / spkts * 1000,
            "dinpkt": dur / np.maximum(dpkts, 1) * 1000,
            "sjit": rng.gamma(2.0, 8.0, n),
            "djit": rng.gamma(2.0, 6.0, n),
            "swin": rng.choice([0, 255], n, p=[0.3, 0.7]),
            "dwin": rng.choice([0, 255], n, p=[0.3, 0.7]),
            "tcprtt": rng.exponential(0.02, n) * answered,
            "synack": rng.exponential(0.01, n) * answered,
            "ackdat": rng.exponential(0.01, n) * answered,
            "smean": sbytes / spkts,
            "dmean": dbytes / np.maximum(dpkts, 1),
            "trans_depth": rng.poisson(0.2, n),
            "response_body_len": rng.poisson(120, n) * (rng.random(n) < 0.2),
            "ct_srv_src": noisy_ct(p["ctsd"]),
            "ct_state_ttl": rng.integers(0, 4, n),
            "ct_dst_ltm": noisy_ct(p["ctdl"]),
            "ct_src_dport_ltm": noisy_ct(max(p["ctdl"] - 1, 1)),
            "ct_dst_sport_ltm": noisy_ct(max(p["ctdl"] - 2, 1)),
            "ct_dst_src_ltm": noisy_ct(p["ctsd"]),
            "is_ftp_login": (rng.random(n) < 0.02).astype(int),
            "ct_ftp_cmd": rng.poisson(0.05, n),
            "ct_flw_http_mthd": rng.poisson(0.3, n),
            "ct_src_ltm": noisy_ct(p["ctsd"]),
            "ct_srv_dst": noisy_ct(p["ctsd"]),
            "is_sm_ips_ports": (rng.random(n) < 0.01).astype(int),
        }
    )
    frame["label"] = int(scenario.endswith("attack"))
    frame["attack_cat"] = {
        "clean_benign": "Normal", "ambiguous_benign": "Normal",
        "clean_attack": "SynthFlood", "ambiguous_attack": "SynthSlowProbe",
    }[scenario]  # fmt: skip
    frame["scenario"] = scenario
    return frame


def generate(seed: int, n_rows: int, id_offset: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    counts = {k: int(round(v * n_rows)) for k, v in MIX.items()}
    counts["clean_benign"] += n_rows - sum(counts.values())
    parts = [_block(rng, c, s) for s, c in counts.items()]
    df = pd.concat(parts, ignore_index=True).sample(frac=1.0, random_state=seed).reset_index(drop=True)
    df.insert(0, "id", np.arange(1, n_rows + 1) + id_offset)
    for col in NUMERIC_FEATURES:
        if df[col].dtype.kind == "f":
            df[col] = df[col].astype(float)
    return df


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, float_format=FLOAT_FORMAT, lineterminator="\n")


def generate_pair(seed: int, out_dir: Path) -> dict[str, Path]:
    """Write synthetic_train.csv and synthetic_test.csv (distinct seeds derived from `seed`)."""
    paths = {"train": out_dir / "synthetic_train.csv", "test": out_dir / "synthetic_test.csv"}
    write_csv(generate(seed, TRAIN_ROWS), paths["train"])
    write_csv(generate(seed + 1, TEST_ROWS), paths["test"])
    return paths


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_test_fixtures(out_dir: Path, seed: int = 42) -> list[Path]:
    """Small fixtures for tests: duplicate event, and several invalid inputs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    base = generate(seed, 40).drop(columns=["scenario"])
    written = []

    def emit(name: str, df: pd.DataFrame) -> None:
        write_csv(df, out_dir / name)
        written.append(out_dir / name)

    emit("clean_small.csv", base)
    emit("duplicate_event.csv", pd.concat([base, base.iloc[[3]]], ignore_index=True))
    emit("invalid_missing_column.csv", base.drop(columns=["ct_srv_dst"]))
    emit("invalid_nonnumeric.csv", base.astype({"dur": object}).assign(dur=lambda d: d["dur"].where(d.index != 5, "n/a")))
    emit("invalid_label.csv", base.assign(label=lambda d: d["label"].where(d.index != 2, 7)))
    emit("invalid_negative.csv", base.assign(sbytes=lambda d: d["sbytes"].where(d.index != 1, -5)))
    return written
