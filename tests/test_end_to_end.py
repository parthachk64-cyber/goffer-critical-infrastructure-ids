"""End-to-end smoke: fixture -> run -> saved report, regeneration, CLI errors, preserved prior runs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from infra_ids.cli import main
from infra_ids.pipeline import run_experiment
from infra_ids.report import resolve_run
from infra_ids.synthetic import generate_pair, sha256_of

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def pair(tmp_path_factory):
    return generate_pair(42, tmp_path_factory.mktemp("fx"))


@pytest.fixture(scope="module")
def run_dir(pair, tmp_path_factory):
    return run_experiment(pair["train"], pair["test"], 42, tmp_path_factory.mktemp("out"), "synthetic_demonstration", max_alerts=None)


def test_run_writes_all_artifacts(run_dir):
    for name in ("manifest.json", "metrics.csv", "predictions.csv", "alerts.jsonl", "queue.jsonl", "report.md", "latency.json"):
        assert (run_dir / name).is_file(), name
    assert (run_dir / "plots" / "confusion_matrices.png").stat().st_size > 1000
    assert (run_dir / "plots" / "precision_recall.png").stat().st_size > 1000


def test_manifest_records_provenance(run_dir, pair):
    m = json.loads((run_dir / "manifest.json").read_text())
    assert m["inputs"]["train"]["sha256"] == sha256_of(pair["train"])
    assert m["seed"] == 42 and m["dependencies"]["scikit-learn"] != "unavailable"
    assert m["analyst_queue"]["policy"].startswith("SIMULATED")
    assert set(m["models"]) == {"majority_reference", "rule_baseline", "decision_tree", "isolation_forest", "mlp", "hybrid_iso_rule"}


def test_predictions_use_opaque_ids_and_no_features(run_dir):
    pred = pd.read_csv(run_dir / "predictions.csv")
    assert pred["row_id"].str.startswith("ev_").all()
    assert "dur" not in pred.columns and "id" not in pred.columns


def test_metrics_counts_are_consistent(run_dir):
    m = pd.read_csv(run_dir / "metrics.csv")
    row = m[(m["subset"] == "all") & (m["model"] == "decision_tree")].iloc[0]
    assert row["tp"] + row["fp"] + row["tn"] + row["fn"] == row["n"]
    assert row["tp"] + row["fn"] == row["positives"]


def test_alerts_match_queue_and_contain_no_feature_values(run_dir):
    alerts = [json.loads(line) for line in (run_dir / "alerts.jsonl").read_text().splitlines()]
    queue = [json.loads(line) for line in (run_dir / "queue.jsonl").read_text().splitlines()]
    assert alerts and {a["event_id"] for a in alerts} == {q["event_id"] for q in queue}
    assert all("dur" not in a for a in alerts)


def test_report_regenerates_identically_from_saved_files(run_dir):
    before = (run_dir / "metrics.csv").read_text()
    (run_dir / "metrics.csv").unlink()
    (run_dir / "plots" / "precision_recall.png").unlink()
    assert main(["report", "--run", str(run_dir)]) == 0
    assert (run_dir / "metrics.csv").read_text() == before
    assert (run_dir / "plots" / "precision_recall.png").is_file()
    assert "SYNTHETIC DEMONSTRATION" in (run_dir / "report.md").read_text()


def test_same_seed_gives_same_predictions_and_prior_runs_are_preserved(pair, run_dir):
    base = run_dir.parent
    second = run_experiment(pair["train"], pair["test"], 42, base, "synthetic_demonstration", max_alerts=None)
    assert second != run_dir and run_dir.is_dir()
    a, b = (pd.read_csv(d / "predictions.csv") for d in (run_dir, second))
    pd.testing.assert_frame_equal(a, b)
    assert resolve_run(base) == second


def test_cli_demo_and_error_paths(tmp_path, capsys):
    assert main(["demo", "--seed", "1", "--out", str(tmp_path / "d")]) == 0
    assert main(["report", "--run", str(tmp_path / "nothing")]) == 2
    assert main(["benchmark", "--train-csv", str(tmp_path / "a.csv"), "--test-csv", str(tmp_path / "b.csv"), "--out", str(tmp_path / "o")]) == 2
    err = capsys.readouterr().err
    assert "input error" in err and "no run found" in err


def test_module_entrypoint_runs():
    out = subprocess.run([sys.executable, "-m", "infra_ids", "--help"], capture_output=True, text=True, check=True)
    assert "demo" in out.stdout and "benchmark" in out.stdout


def test_committed_fixture_checksums_match_regeneration(tmp_path):
    sums = (ROOT / "data" / "fixtures" / "SHA256SUMS").read_text().split()
    committed = dict(zip(sums[1::2], sums[0::2], strict=True))
    paths = generate_pair(42, tmp_path)
    for name, p in paths.items():
        assert committed[p.name] == sha256_of(p), name
