"""Behavioural tests: schema, leakage, train-only transforms, thresholds, metrics, duplicates, transitions."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from infra_ids.detectors import IsolationDetector, rule_reasons
from infra_ids.evaluate import (
    average_precision,
    confusion,
    metric_row,
    metrics_from_counts,
    select_threshold,
)
from infra_ids.features import Preprocessor
from infra_ids.ingest import load_csv, opaque_row_id
from infra_ids.response import AnalystQueue, InvalidTransition
from infra_ids.schema import FORBIDDEN_INPUTS, SchemaError, assert_no_leakage
from infra_ids.splits import overlap_report, validation_split
from infra_ids.synthetic import generate
from infra_ids.triage import build_alerts

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def clean() -> pd.DataFrame:
    return load_csv(FIX / "clean_small.csv", "train").frame


# --- schema validation -------------------------------------------------------------------------
@pytest.mark.parametrize(
    "name,fragment",
    [
        ("invalid_missing_column.csv", "missing required columns"),
        ("invalid_nonnumeric.csv", "non-numeric"),
        ("invalid_label.csv", "must be 0 or 1"),
        ("invalid_negative.csv", "negative"),
    ],
)
def test_invalid_inputs_are_rejected_with_actionable_message(name, fragment):
    with pytest.raises(SchemaError) as exc:
        load_csv(FIX / name, "train")
    assert fragment in str(exc.value)


def test_missing_file_and_wrong_suffix(tmp_path):
    with pytest.raises(SchemaError, match="not found"):
        load_csv(tmp_path / "nope.csv", "train")
    txt = tmp_path / "x.txt"
    txt.write_text("a")
    with pytest.raises(SchemaError, match=".csv"):
        load_csv(txt, "train")


def test_empty_csv_rejected(tmp_path):
    p = tmp_path / "e.csv"
    p.write_text("id,label\n")
    with pytest.raises(SchemaError):
        load_csv(p, "train")


def test_row_ids_are_opaque_stable_and_partition_scoped(clean):
    assert clean["row_id"].is_unique
    assert opaque_row_id("train", 1) == opaque_row_id("train", 1)
    assert opaque_row_id("train", 1) != opaque_row_id("test", 1)
    assert "id" not in clean.columns


# --- label leakage -----------------------------------------------------------------------------
def test_forbidden_columns_never_reach_model_inputs(clean):
    pre = Preprocessor().fit(clean)
    assert not any(n.split("=")[0] in FORBIDDEN_INPUTS for n in pre.feature_names_)
    with pytest.raises(SchemaError):
        assert_no_leakage(["dur", "label"])


def test_extra_columns_are_ignored_and_reported():
    df = generate(1, 30)  # carries a `scenario` column
    p = Path(__file__).parent / "_tmp_extra.csv"
    try:
        df.to_csv(p, index=False)
        ing = load_csv(p, "train")
    finally:
        p.unlink(missing_ok=True)
    assert "scenario" in ing.manifest["ignored_columns"]
    assert "scenario" not in ing.frame.columns


# --- train-only transformations ----------------------------------------------------------------
def test_preprocessor_uses_training_statistics_only(clean):
    train, other = clean.iloc[:20], clean.iloc[20:].copy()
    other["sbytes"] = other["sbytes"] * 1000  # a shifted partition must not move the fitted stats
    pre = Preprocessor().fit(train)
    mean_before = pre.mean_.copy()
    pre.transform(other)
    np.testing.assert_array_equal(mean_before, pre.mean_)
    z_train = pre.transform(train)
    assert abs(z_train[:, 0].mean()) < 1e-9  # standardised on its own fit data


def test_transform_before_fit_fails(clean):
    with pytest.raises(RuntimeError):
        Preprocessor().transform(clean)


def test_unseen_category_maps_to_other(clean):
    pre = Preprocessor().fit(clean)
    novel = clean.iloc[:2].copy()
    novel["proto"] = "never-seen"
    X = pre.transform(novel)
    idx = pre.feature_names_.index("proto=__other__")
    assert (X[:, idx] == 1).all()


def test_isolation_detector_fits_on_normal_rows_only(clean):
    pre = Preprocessor().fit(clean)
    X, y = pre.transform(clean), clean["label"].to_numpy()
    det = IsolationDetector(seed=1).fit(X, y, clean)
    assert len(det.ref_) == int((y == 0).sum())
    s = det.score(X, clean)
    assert ((s >= 0) & (s <= 1)).all()


# --- reproducibility ---------------------------------------------------------------------------
def test_synthetic_generation_is_deterministic():
    pd.testing.assert_frame_equal(generate(7, 50), generate(7, 50))
    assert not generate(7, 50).equals(generate(8, 50))


def test_predictions_are_reproducible(clean):
    def scores(seed):
        pre = Preprocessor().fit(clean)
        X, y = pre.transform(clean), clean["label"].to_numpy()
        return IsolationDetector(seed=seed).fit(X, y, clean).score(X, clean)

    np.testing.assert_array_equal(scores(3), scores(3))


# --- thresholds, metrics, undefined denominators -------------------------------------------------
def test_threshold_boundary_is_inclusive():
    y = np.array([0, 0, 1, 1])
    s = np.array([0.1, 0.4, 0.4, 0.9])
    t = select_threshold(y, s)
    pred = (s >= t).astype(int)
    assert confusion(y, pred)["tp"] >= 1
    row = metric_row("m", y, s, 0.4, True)
    assert row["tp"] == 2 and row["fp"] == 1  # score == threshold is flagged


def test_confusion_matches_hand_calculation():
    y = np.array([1, 1, 1, 0, 0, 0, 0, 1])
    p = np.array([1, 0, 1, 1, 0, 0, 0, 1])
    c = confusion(y, p)
    assert c == {"tp": 3, "fp": 1, "tn": 3, "fn": 1}
    m = metrics_from_counts(c)
    assert m["accuracy"] == pytest.approx(6 / 8)
    assert m["precision"] == pytest.approx(3 / 4)
    assert m["recall"] == pytest.approx(3 / 4)
    assert m["f1"] == pytest.approx(0.75)
    assert m["fpr"] == pytest.approx(1 / 4)


def test_zero_positive_case_is_explicit_not_zero():
    y = np.zeros(5, dtype=int)
    s = np.linspace(0, 1, 5)
    t = select_threshold(y, s)
    assert (s >= t).sum() == 0  # nothing flagged
    m = metrics_from_counts(confusion(y, np.zeros(5, dtype=int)))
    assert m["recall"] is None and m["precision"] is None and m["f1"] is None
    assert average_precision(y, s, True) is None


def test_average_precision_skipped_for_reference_scores():
    assert average_precision([0, 1, 1], [0.5, 0.5, 0.5], meaningful=False) is None


# --- rule and triage -----------------------------------------------------------------------------
def test_rule_reasons_codes():
    raw = pd.DataFrame({"ct_srv_dst": [9, 1], "ct_dst_ltm": [9, 1], "dpkts": [5, 0], "spkts": [3, 4]})
    r = rule_reasons(raw)
    assert r[0] == ["R1_FANIN_BURST"]
    assert r[1] == ["R2_UNANSWERED"]


def test_alerts_have_required_fields_and_respect_threshold_and_cap():
    ids = np.array(["a", "b", "c", "d"])
    scores = np.array([0.95, 0.2, 0.7, 0.99])
    alerts, info = build_alerts(ids, scores, 0.7, "m", "v1", lambda i: ["R1_FANIN_BURST"] if i == 3 else [], max_alerts=2)
    assert [a["event_id"] for a in alerts] == ["d", "a"]
    assert info == {"flagged": 3, "written": 2, "truncated": True}
    a = alerts[0]
    assert set(a) >= {"event_id", "model", "model_version", "risk_score", "threshold", "reason_codes", "proposed_action"}
    assert a["proposed_action"] == "expedite_analyst_review"
    assert alerts[1]["proposed_action"] == "analyst_review"


# --- duplicates and splits -------------------------------------------------------------------
def test_duplicate_event_ids_keep_first_and_are_counted():
    ing = load_csv(FIX / "duplicate_event.csv", "train")
    assert ing.manifest["duplicate_ids_dropped"] == 1
    assert ing.manifest["rows_kept"] == 40
    assert ing.frame["row_id"].is_unique


def test_validation_split_is_seeded_and_keeps_duplicates_together(clean):
    doubled = pd.concat([clean, clean], ignore_index=True)
    a1, b1 = validation_split(doubled, 0.25, 5)
    a2, b2 = validation_split(doubled, 0.25, 5)
    np.testing.assert_array_equal(b1, b2)
    from infra_ids.splits import feature_hash

    h = feature_hash(doubled)
    assert not (set(h.iloc[a1]) & set(h.iloc[b1]))
    with pytest.raises(ValueError):
        validation_split(doubled, 1.5, 1)


def test_overlap_report_counts_exact_duplicates(clean):
    test = pd.concat([clean.iloc[:3], generate(99, 5).assign(label=0, attack_cat="")[clean.columns.drop("row_id")].assign(row_id="x")])
    rep = overlap_report(clean, test.reset_index(drop=True))
    assert rep["test_rows_with_exact_train_duplicate"] == 3
    assert rep["of_which_label_disagrees_with_train"] == 0


# --- disposition workflow ------------------------------------------------------------------------
def _alert(eid="ev_1"):
    return {"event_id": eid, "risk_score": 0.9, "reason_codes": ["SCORE_ABOVE_THRESHOLD"], "proposed_action": "analyst_review"}


def test_legal_transitions_and_history(tmp_path):
    q = AnalystQueue(tmp_path / "q.jsonl")
    assert q.enqueue(_alert())
    q.transition("ev_1", "reviewed", "looked", "analyst")
    q.transition("ev_1", "escalated", "needs follow-up", "analyst")
    assert [h["to"] for h in q.history("ev_1")] == ["open", "reviewed", "escalated"]
    assert all(h["at"] for h in q.history("ev_1"))


@pytest.mark.parametrize("path", [["dismissed"], ["escalated"], ["reviewed", "open"]])
def test_illegal_transitions_raise(tmp_path, path):
    q = AnalystQueue(tmp_path / "q.jsonl")
    q.enqueue(_alert())
    with pytest.raises(InvalidTransition):
        for step in path:
            q.transition("ev_1", step, "r", "a")


def test_terminal_states_and_blank_reason_rejected(tmp_path):
    q = AnalystQueue(tmp_path / "q.jsonl")
    q.enqueue(_alert())
    q.transition("ev_1", "reviewed", "r", "a")
    with pytest.raises(InvalidTransition):
        q.transition("ev_1", "dismissed", "  ", "a")
    q.transition("ev_1", "dismissed", "benign", "a")
    with pytest.raises(InvalidTransition):
        q.transition("ev_1", "escalated", "again", "a")
    with pytest.raises(InvalidTransition):
        q.transition("ev_missing", "reviewed", "r", "a")


def test_duplicate_alert_keeps_single_history_and_survives_reload(tmp_path):
    p = tmp_path / "q.jsonl"
    q = AnalystQueue(p)
    assert q.enqueue(_alert()) is True
    q.transition("ev_1", "reviewed", "r", "a")
    assert q.enqueue(_alert()) is False  # reprocessed event: no reset, no second history
    assert q.state("ev_1") == "reviewed"
    reloaded = AnalystQueue(p)
    assert reloaded.state("ev_1") == "reviewed" and len(reloaded.history("ev_1")) == 2
