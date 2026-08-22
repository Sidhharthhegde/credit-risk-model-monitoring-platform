from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from credit_risk_monitoring.data_quality.engine import DataQualityMonitor


def _monitor() -> DataQualityMonitor:
    contract = {
        "threshold_binding": {
            "missing_rate_absolute_change": {"warning": 0.02, "critical": 0.05},
            "unknown_category_share": {"warning": 0.01, "critical": 0.05},
        }
    }
    schema = pd.DataFrame(
        {
            "Raw_Feature_Index": [0, 1, 2],
            "Raw_Feature_Name": ["num", "cat", "binary"],
            "Feature_Class": ["NUMERIC", "CATEGORICAL", "BINARY"],
        }
    )
    missing = pd.DataFrame({"feature": ["num", "cat", "binary"], "missing_rate": [0.0, 0.0, 0.0]})
    numeric = pd.DataFrame({"feature": ["num"], "min": [0.0], "max": [10.0]})
    categorical = pd.DataFrame({"feature": ["cat"], "reference_category": ["known"]})
    return DataQualityMonitor(contract, schema, missing, numeric, categorical)


def test_duplicate_identifier_hard_fails_before_feature_controls() -> None:
    frame = pd.DataFrame(
        {"SK_ID_CURR": [1, 1], "num": [1.0, 2.0], "cat": ["known", "known"], "binary": [0, 1]}
    )
    result = _monitor().evaluate(
        frame, artifact_id="HARD", scenario_id="SIM-M05",
        source_context={"authoritative_use_permitted": False}, expected_rows=1,
    )
    assert result.summary["dq_control_decision"] == "HARD_FAIL"
    assert result.summary["downstream_monitoring_eligible"] is False
    assert result.completeness.empty and result.novelty.empty and result.ranges.empty


def test_unseen_category_is_measured_not_contract_rejected() -> None:
    frame = pd.DataFrame(
        {"SK_ID_CURR": range(100), "num": [1.0] * 100, "cat": ["novel"] * 5 + ["known"] * 95, "binary": [0] * 100}
    )
    result = _monitor().evaluate(
        frame, artifact_id="VALID", scenario_id="SIM-M05",
        source_context={"authoritative_use_permitted": True}, expected_rows=100,
    )
    novelty = result.novelty.iloc[0]
    assert novelty["value"] == 0.05
    assert novelty["severity"] == "CRITICAL"
    assert novelty["contract_valid"]
    assert result.summary["contract_status"] == "PASS"


def test_finite_range_excursion_is_supporting_and_not_a_hard_failure() -> None:
    frame = pd.DataFrame(
        {"SK_ID_CURR": [1], "num": [1000.0], "cat": ["known"], "binary": [1]}
    )
    result = _monitor().evaluate(
        frame, artifact_id="TAIL", scenario_id="SIM-M05",
        source_context={"authoritative_use_permitted": True}, expected_rows=1,
    )
    assert result.ranges.iloc[0]["severity"] == "N/A"
    assert result.ranges.iloc[0]["contract_valid"]
    assert result.summary["contract_status"] == "PASS"


def test_source_authority_is_independent_of_contract_validity() -> None:
    frame = pd.DataFrame(
        {"SK_ID_CURR": [1], "num": [1.0], "cat": ["known"], "binary": [1]}
    )
    result = _monitor().evaluate(
        frame, artifact_id="SOURCE", scenario_id="SIM-M05",
        source_context={
            "availability_state": "SOURCE_DEGRADED",
            "governance_state": "SOURCE_POLICY_REQUIRED",
            "fallback_status": "NO_APPROVED_FALLBACK",
            "authoritative_use_permitted": False,
            "selected_row_count": 1,
        }, expected_rows=1,
    )
    assert result.summary["contract_status"] == "PASS"
    assert result.summary["dq_control_decision"] == "NON_AUTHORITATIVE"
    assert result.source["availability"]["control_role"] == "DIRECT"
    assert result.source["availability"]["availability_state"] == "SOURCE_DEGRADED"
    assert result.source["availability"]["result"] == "FINDING"
    assert result.source["authority"]["control_role"] == "HARD_GATE"
    assert result.source["authority"]["result"] == "FAIL"


def test_phase6_final_decision_preserves_scope_gate_when_present() -> None:
    root = Path(__file__).resolve().parents[2]
    decision = root / "reports/monitoring/DATA-QUALITY-CONTROL-01/phase6_completion_decision.json"
    if decision.exists():
        payload = json.loads(decision.read_text())
        assert payload["technical_qualification"] == "PASS"
        assert payload["review_decision"] == "APPROVED"
        assert payload["phase_6_complete"] is True
        assert payload["phase_7_authorized"] is True
        assert payload["monitoring_alerts_generated"] is False
