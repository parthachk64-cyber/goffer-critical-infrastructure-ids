"""Public result tables: Table A counts, Table B/C derivation, README regeneration and the read-only check."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from infra_ids import results
from infra_ids.cli import main
from infra_ids.evaluate import metric_row
from infra_ids.pipeline import run_experiment
from infra_ids.synthetic import generate_pair
from infra_ids.train import MODEL_ORDER

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "data" / "paper" / "energy_case_matrix.csv"


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    fx = generate_pair(42, tmp_path_factory.mktemp("fx"))
    return run_experiment(fx["train"], fx["test"], 42, tmp_path_factory.mktemp("out"), "synthetic_demonstration", max_alerts=50)


@pytest.fixture()
def workspace(run, tmp_path):
    """A private copy of README, docs/results.md, the matrix and a run, so tests can rewrite them."""
    for rel in ("README.md", "docs/results.md", "data/paper/energy_case_matrix.csv"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, tmp_path / rel)
    shutil.copytree(run, tmp_path / "run")
    return tmp_path


def cli_args(ws: Path, *extra: str) -> list[str]:
    return ["report", "--run", str(ws / "run"), "--readme", str(ws / "README.md"), "--results-md", str(ws / "docs/results.md"),
            "--energy-matrix", str(ws / "data/paper/energy_case_matrix.csv"),
            "--energy-counts", str(ws / "data/paper/energy_case_counts.csv"), *extra]  # fmt: skip


# ------------------------------------------------------------------------------------------ Table A


def test_table_a_counts_for_the_three_verified_rows():
    rows = {r["feature"]: r for r in results.energy_counts(MATRIX)}
    for feat, marked in (("Phishing", 3), ("Ransomware deployment", 1), ("SCADA exploitation", 2)):
        assert (rows[feat]["case_columns_marked"], rows[feat]["case_columns_examined"]) == (marked, 4), feat


def test_table_a_all_nine_features_present_with_four_cases_examined():
    rows = results.energy_counts(MATRIX)
    assert len(rows) == 9 and all(r["case_columns_examined"] == 4 and r["unspecified_cells"] == 0 for r in rows)


def test_missing_cell_is_not_a_cross_and_is_not_examined(tmp_path):
    f = tmp_path / "m.csv"
    f.write_text("feature,colonial_pipeline_2021,ukraine_power_grid_2015_2016,triton_2017,blackenergy_2014\n"
                 "Phishing,marked,not_marked,,marked\n", encoding="utf-8")  # fmt: skip
    r = results.energy_counts(f)[0]
    assert (r["case_columns_marked"], r["case_columns_examined"], r["unspecified_cells"]) == (2, 3, 1)


def test_unknown_cell_code_is_rejected(tmp_path):
    f = tmp_path / "m.csv"
    f.write_text("feature,colonial_pipeline_2021,ukraine_power_grid_2015_2016,triton_2017,blackenergy_2014\nX,yes,marked,marked,marked\n",
                 encoding="utf-8")  # fmt: skip
    with pytest.raises(ValueError, match="unknown cell code"):
        results.energy_counts(f)


def test_committed_counts_csv_matches_the_matrix():
    assert (ROOT / "data/paper/energy_case_counts.csv").read_text(encoding="utf-8") == results.energy_counts_csv(MATRIX)


# ------------------------------------------------------------------------------------------ Table B


def test_table_b_has_six_models_on_identical_test_ids(run):
    pred = pd.read_csv(run / "predictions.csv")
    rows = list(csv.DictReader(open(run / "table_b.csv", encoding="utf-8")))
    assert [r["model"] for r in rows] == list(MODEL_ORDER) and len(rows) == 6
    assert {int(r["test_n"]) for r in rows} == {len(pred)}
    assert pred["row_id"].is_unique


def test_confusion_counts_sum_to_test_n(run):
    for r in csv.DictReader(open(run / "table_b.csv", encoding="utf-8")):
        assert int(r["tp"]) + int(r["fp"]) + int(r["tn"]) + int(r["fn"]) == int(r["test_n"]), r["model"]
        assert int(r["tp"]) + int(r["fn"]) == int(r["positives"])


def test_table_b_matches_a_hand_calculated_example():
    pred = pd.DataFrame({"y_true": [1, 1, 1, 0, 0, 0, 0, 0]} | {f"pred_{m}": [1, 1, 0, 1, 0, 0, 0, 0] for m in MODEL_ORDER})
    man = {"run_id": "r", "dataset_label": "d", "models": {m: {"threshold": 0.5} for m in MODEL_ORDER}}
    r = results.table_b_rows(pred, man)[0]
    assert (r["tp"], r["fp"], r["tn"], r["fn"]) == (2, 1, 4, 1)
    assert r["precision"] == pytest.approx(2 / 3) and r["recall"] == pytest.approx(2 / 3)
    assert r["f1"] == pytest.approx(2 / 3) and r["fpr"] == pytest.approx(1 / 5) and r["accuracy"] == pytest.approx(6 / 8)


def test_undefined_ratios_are_none_not_zero():
    pred = pd.DataFrame({"y_true": [0, 0, 0]} | {f"pred_{m}": [0, 0, 0] for m in MODEL_ORDER})
    man = {"run_id": "r", "dataset_label": "d", "models": {m: {"threshold": 0.5} for m in MODEL_ORDER}}
    r = results.table_b_rows(pred, man)[0]
    assert r["precision"] is None and r["recall"] is None and r["f1"] is None and r["fpr"] == 0.0


def test_metrics_count_saved_decisions_not_rounded_scores():
    # score 0.5806451612903226 rounds to 0.580645 on disk; re-thresholding the rounded score would flip this record
    row = metric_row("m", [1], [0.580645], 0.5806451612903226, True, decisions=[1])
    assert row["tp"] == 1 and row["fn"] == 0
    assert metric_row("m", [1], [0.580645], 0.5806451612903226, True)["fn"] == 1


# ------------------------------------------------------------------------------------------ Table C


def test_false_alert_rate_uses_the_benign_denominator(run):
    rows = list(csv.DictReader(open(run / "table_c.csv", encoding="utf-8")))
    for r in rows:
        benign = int(r["fp"]) + int(r["tn"])
        assert int(r["benign_records"]) == benign
        assert float(r["false_alerts_per_1000_benign"]) == pytest.approx(1000 * int(r["fp"]) / benign)


def test_false_alert_rate_is_empty_when_there_are_no_benign_records():
    b = [{"model": "m", "tp": 3, "fp": 0, "tn": 0, "fn": 1}]
    assert results.table_c_rows(b, None)[0]["false_alerts_per_1000_benign"] is None


def test_timing_is_measured_with_samples_for_a_new_run(run):
    lat = json.loads((run / "latency.json").read_text(encoding="utf-8"))
    assert len(lat["models"]["mlp"]["samples_ms"]) == lat["models"]["mlp"]["repeats"]
    rows = list(csv.DictReader(open(run / "table_c.csv", encoding="utf-8")))
    assert all(r["timing_status"] == "measured" and r["batch_size"] == str(lat["batch_size"]) for r in rows)


def test_absent_or_failed_timing_is_reported_with_a_reason():
    b = [{"model": "mlp", "tp": 1, "fp": 1, "tn": 1, "fn": 1}]
    assert "latency.json absent" in results.table_c_rows(b, None)[0]["timing_status"]
    failed = results.table_c_rows(b, {"batch_size": 8, "models": {"mlp": {"p50_ms": None, "p95_ms": None}}})[0]
    assert failed["timing_status"].startswith("unavailable") and failed["p50_ms"] == ""
    assert results.table_c_rows(b, {"batch_size": 8, "models": {}})[0]["timing_status"].startswith("unavailable")


def test_paired_comparison_counts_gained_and_lost_on_identical_records():
    y = [1, 1, 1, 0, 0, 0]
    iso = [1, 0, 0, 1, 1, 0]
    hyb = [1, 1, 0, 1, 0, 1]
    pred = pd.DataFrame({"y_true": y, "pred_isolation_forest": iso, "pred_hybrid_iso_rule": hyb})
    man = {"run_id": "r", "models": {"isolation_forest": {"threshold": 0.1}, "hybrid_iso_rule": {"threshold": 0.2}}}
    p = results.paired_row(pred, man)
    assert (p["gained_true_detections"], p["lost_true_detections"], p["net_extra_true_detections"]) == (1, 0, 1)
    assert (p["gained_false_alerts"], p["lost_false_alerts"], p["net_extra_false_alerts"]) == (1, 1, 0)


# ------------------------------------------------------------------------------------------ README regeneration


def test_update_is_byte_identical_when_repeated(workspace):
    assert main(cli_args(workspace, "--update-readme")) == 0
    first = [(workspace / p).read_bytes() for p in ("README.md", "docs/results.md", "run/table_b.csv", "run/table_c.csv")]
    assert main(cli_args(workspace, "--update-readme")) == 0
    again = [(workspace / p).read_bytes() for p in ("README.md", "docs/results.md", "run/table_b.csv", "run/table_c.csv")]
    assert first == again


def test_readme_tables_contain_the_run_numbers(workspace):
    main(cli_args(workspace, "--update-readme"))
    text = (workspace / "README.md").read_text(encoding="utf-8")
    rows = list(csv.DictReader(open(workspace / "run/table_b.csv", encoding="utf-8")))
    assert "Synthetic demo results" in text and "pending" in text
    for r in rows:
        assert f"| {results.NAMES[r['model']]} | {int(r['test_n']):,} |" in text
    assert "| Phishing | 3 | 4 |" in text and "| Ransomware deployment | 1 | 4 |" in text and "| SCADA exploitation | 2 | 4 |" in text


def test_check_passes_after_update_and_does_not_write(workspace, capsys):
    main(cli_args(workspace, "--update-readme"))
    before = (workspace / "README.md").read_bytes()
    assert main(cli_args(workspace, "--check")) == 0
    assert (workspace / "README.md").read_bytes() == before


def test_check_detects_stale_readme_table_without_rewriting(workspace, capsys):
    main(cli_args(workspace, "--update-readme"))
    p = workspace / "README.md"
    stale = p.read_text(encoding="utf-8").replace("| Phishing | 3 | 4 |", "| Phishing | 4 | 4 |")
    p.write_text(stale, encoding="utf-8")
    assert main(cli_args(workspace, "--check")) == 1
    assert "stale" in capsys.readouterr().err
    assert p.read_text(encoding="utf-8") == stale  # read-only


def test_check_detects_stale_csv_and_stale_results_doc(workspace):
    main(cli_args(workspace, "--update-readme"))
    t = workspace / "run/table_b.csv"
    t.write_text(t.read_text(encoding="utf-8").replace(",0.5,", ",0.6,", 1), encoding="utf-8")
    assert main(cli_args(workspace, "--check")) == 1
    main(cli_args(workspace, "--update-readme"))
    d = workspace / "docs/results.md"
    d.write_text(d.read_text(encoding="utf-8").replace("| TP |", "| tp |"), encoding="utf-8")
    assert main(cli_args(workspace, "--check")) == 1


def test_check_and_update_cannot_be_combined(workspace):
    assert main(cli_args(workspace, "--check", "--update-readme")) == 2


def test_missing_marker_gives_an_actionable_error(workspace):
    p = workspace / "README.md"
    p.write_text(p.read_text(encoding="utf-8").replace("<!-- BEGIN GENERATED:table-b -->", ""), encoding="utf-8")
    with pytest.raises(ValueError, match="marker pair for 'table-b' not found"):
        main(cli_args(workspace, "--update-readme"))


def test_check_without_predictions_uses_committed_csvs_and_flags_inconsistency(workspace):
    main(cli_args(workspace, "--update-readme"))
    (workspace / "run/predictions.csv").unlink()
    assert main(cli_args(workspace, "--check")) == 0
    t = workspace / "run/table_b.csv"
    rows = t.read_text(encoding="utf-8").splitlines()
    header = rows[0].split(",")
    cells = rows[1].split(",")
    cells[header.index("tp")] = str(int(cells[header.index("tp")]) + 1)
    t.write_text("\n".join([rows[0], ",".join(cells), *rows[2:]]) + "\n", encoding="utf-8")
    assert main(cli_args(workspace, "--check")) == 1


# ------------------------------------------------------------------------------------------ committed repository state


def test_committed_readme_and_csvs_are_current_with_the_committed_benchmark_run():
    run = ROOT / "results" / "unsw-nb15-example"
    if not run.exists():
        pytest.skip("committed benchmark example absent")
    assert main(["report", "--run", str(run), "--check", "--readme", str(ROOT / "README.md"),
                 "--results-md", str(ROOT / "docs/results.md"), "--energy-matrix", str(MATRIX),
                 "--energy-counts", str(ROOT / "data/paper/energy_case_counts.csv")]) == 0  # fmt: skip


def test_committed_readme_results_section_precedes_installation_details():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert text.index("## Results") < text.index("## Five-minute quick start")
    for name in ("table-a", "table-b"):
        assert f"<!-- BEGIN GENERATED:{name} -->" in text and f"<!-- END GENERATED:{name} -->" in text


def test_ratio_helpers_do_not_divide_by_zero():
    assert results._ratio(1, 0) is None and results._f(None) == "n/a" and results._f(np.nan) == "n/a"
