from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from credit_risk_monitoring.prediction.engine import apply_threshold
from credit_risk_monitoring.segment.engine import SegmentDefinition, assign_segment, evidence_status


def _definition(family_id: str, features: tuple[str, ...], levels: tuple[str, ...]) -> SegmentDefinition:
    return SegmentDefinition(family_id, family_id, features, levels, False, "TEST_FROZEN_DEFINITION")


def test_binary_joint_and_external_availability_assignments_are_deterministic() -> None:
    frame = pd.DataFrame({
        "HAS_BUREAU_HISTORY": [0, 1], "HAS_PREV_APP_HISTORY": [1, 0],
        "EXT_SOURCE_1": [None, 0.1], "EXT_SOURCE_2": [0.2, 0.2], "EXT_SOURCE_3": [None, 0.3],
    })
    binary = _definition("SG-01", ("HAS_BUREAU_HISTORY",), ("0", "1"))
    joint = _definition("SG-03", ("HAS_BUREAU_HISTORY", "HAS_PREV_APP_HISTORY"), ("BUREAU_0_PREV_1", "BUREAU_1_PREV_0"))
    external = _definition("SG-08", ("EXT_SOURCE_1", "EXT_SOURCE_2", "EXT_SOURCE_3"), ("0", "1", "2", "3"))
    assert assign_segment(frame, binary).tolist() == ["0", "1"]
    assert assign_segment(frame, joint).tolist() == ["BUREAU_0_PREV_1", "BUREAU_1_PREV_0"]
    assert assign_segment(frame, external).tolist() == ["1", "3"]
    assert assign_segment(frame, joint).equals(assign_segment(frame.copy(deep=True), joint))


def test_age_boundaries_follow_frozen_part_a_definition() -> None:
    frame = pd.DataFrame({"DAYS_BIRTH": [0.0, -30 * 365.25, -45 * 365.25, -60 * 365.25]})
    definition = _definition("SG-10", ("DAYS_BIRTH",), ("[0,30)", "[30,45)", "[45,60)", "[60,+inf)"))
    assert assign_segment(frame, definition).tolist() == ["[0,30)", "[30,45)", "[45,60)", "[60,+inf)"]


def test_unexpected_or_missing_values_are_explicitly_unclassifiable() -> None:
    frame = pd.DataFrame({"REGION_RATING_CLIENT": [1, 4, None]})
    definition = _definition("SG-11", ("REGION_RATING_CLIENT",), ("1", "2", "3"))
    assigned = assign_segment(frame, definition)
    assert assigned.tolist() == ["1", "__UNCLASSIFIABLE__", "__UNCLASSIFIABLE__"]
    assert (~assigned.isin(definition.levels)).sum() == 2


def test_discrimination_sufficiency_boundaries_are_independent() -> None:
    assert evidence_status(999, 50, minimum_n=1000) == "INSUFFICIENT_DATA"
    assert evidence_status(1000, 50, minimum_n=1000) == "ELIGIBLE"
    assert evidence_status(1000, 49, minimum_n=1000) == "INSUFFICIENT_DATA"
    assert evidence_status(1000, 951, minimum_n=1000) == "INSUFFICIENT_DATA"


def test_threshold_sufficiency_boundaries_are_independent() -> None:
    assert evidence_status(499, 50, minimum_n=500) == "INSUFFICIENT_DATA"
    assert evidence_status(500, 50, minimum_n=500) == "ELIGIBLE"
    assert evidence_status(500, 49, minimum_n=500) == "INSUFFICIENT_DATA"
    assert evidence_status(500, 451, minimum_n=500) == "INSUFFICIENT_DATA"


def test_frozen_threshold_boundary_remains_greater_than_or_equal() -> None:
    assert apply_threshold(pd.Series([0.079999, 0.08, 0.080001]).to_numpy()).tolist() == [
        "risk_negative", "risk_positive", "risk_positive",
    ]


def test_phase10_final_scope_and_outcome_isolation_when_present() -> None:
    root = Path(__file__).resolve().parents[2]
    report = root / "reports/monitoring/SEGMENT-MONITORING-01"
    if report.exists():
        decision = json.loads((report / "phase10_completion_decision.json").read_text(encoding="utf-8"))
        assert decision["technical_qualification"] == "PASS"
        assert decision["review_decision"] == "APPROVED"
        assert decision["phase_10_complete"] is True
        assert decision["phase_11_authorized"] is True
        assert decision["new_segments_created"] is False
        assert decision["post_result_segment_consolidation"] is False
        assert decision["m06_discrimination_eligible_segments"] == 21
        assert decision["m06_discrimination_insufficient_segments"] == 11
        assert decision["m06_threshold_eligible_segments"] == 26
        assert decision["m06_threshold_insufficient_segments"] == 6
        for scenario in range(1, 6):
            assert decision[f"m0{scenario}_outcome_segment_results"] == "NOT_ASSESSABLE"
        scope = json.loads((report / "scope_protection_attestation.json").read_text(encoding="utf-8"))
        assert scope["monitoring_alerts_generated"] is False
        assert scope["overall_model_health_calculated"] is False
        assert scope["fairness_certification"] is False
