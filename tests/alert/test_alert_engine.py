from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from credit_risk_monitoring.alert.engine import (
    AlertEngine,
    PerformanceControlPolicy,
    aggregate_health,
    deterministic_alert_id,
    persistence_sequence,
    transition_alert_status,
)


def _performance_policy() -> PerformanceControlPolicy:
    rule = {
        "reference_value": 0.8, "bootstrap_standard_deviation": 0.01,
        "warning_lower": 0.78, "warning_upper": 0.82,
        "critical_lower": 0.76, "critical_upper": 0.84,
        "adverse_direction": "LOWER_IS_ADVERSE",
    }
    return PerformanceControlPolicy({"metrics": {"roc_auc": rule}})


def _candidate(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "run_id": "RUN-01", "scenario_id": "SIM-X", "artifact_id": "ART-01",
        "component": "FEATURE_DRIFT", "alert_class": "FEATURE_DRIFT", "metric_id": "feature_psi",
        "entity_type": "FEATURE", "entity_id": "X", "metric_value": 0.3,
        "metric_severity": "CRITICAL", "evidence_status": "ELIGIBLE",
        "control_role": "DIRECT_ALERT_DRIVER", "evidence_type": "MONITORING_EVIDENCE",
        "source_phase": "PHASE_7", "source_artifact_hash": "abc",
    }
    row.update(overrides)
    return row


def test_alert_ids_are_deterministic_and_content_keyed() -> None:
    first = deterministic_alert_id("XGBT-01", "RUN", "FEATURE_DRIFT", "feature_psi", "EXT_SOURCE_2")
    second = deterministic_alert_id("XGBT-01", "RUN", "FEATURE_DRIFT", "feature_psi", "EXT_SOURCE_2")
    assert first == second
    assert first != deterministic_alert_id("XGBT-01", "RUN", "FEATURE_DRIFT", "feature_psi", "EXT_SOURCE_3")


def test_supporting_and_derived_candidates_cannot_create_alerts() -> None:
    engine = AlertEngine(_performance_policy(), {"X"})
    rows = pd.DataFrame([
        _candidate(control_role="SUPPORTING_CORROBORATION"),
        _candidate(control_role="DERIVED_ONLY", metric_id="gini"),
        _candidate(evidence_status="NOT_ASSESSABLE"),
        _candidate(metric_severity="NORMAL"),
    ])
    assert engine.qualify(rows).empty


def test_feature_criticality_changes_alert_priority_not_metric_severity() -> None:
    rows = pd.DataFrame([_candidate(entity_id="CRITICAL_X"), _candidate(entity_id="OTHER_X", run_id="RUN-02")])
    alerts = AlertEngine(_performance_policy(), {"CRITICAL_X"}).qualify(rows)
    critical = alerts.loc[alerts["entity_id"] == "CRITICAL_X"].iloc[0]
    other = alerts.loc[alerts["entity_id"] == "OTHER_X"].iloc[0]
    assert critical["metric_severity"] == "CRITICAL" and critical["alert_severity"] == "CRITICAL"
    assert other["metric_severity"] == "CRITICAL" and other["alert_severity"] == "WARNING"


def test_performance_policy_requires_control_and_material_breach() -> None:
    policy = _performance_policy()
    assert policy.severity("roc_auc", 0.79)[0] == "NORMAL"
    assert policy.severity("roc_auc", 0.77)[0] == "WARNING"
    assert policy.severity("roc_auc", 0.75)[0] == "CRITICAL"


def test_overall_health_keeps_authorization_and_completeness_independent() -> None:
    assert aggregate_health(["CRITICAL", "NORMAL"], authorization_status="AUTHORIZED", evidence_complete=False) == "CRITICAL"
    assert aggregate_health(["WARNING", "NORMAL"], authorization_status="AUTHORIZED", evidence_complete=False) == "WARNING"
    assert aggregate_health(["NORMAL", "NORMAL"], authorization_status="AUTHORIZED", evidence_complete=True) == "NORMAL"
    assert aggregate_health(["NORMAL", "NORMAL"], authorization_status="AUTHORIZED", evidence_complete=False) == "NOT_ASSESSABLE"
    assert aggregate_health(["CRITICAL"], authorization_status="BLOCKED_HARD_GATE", evidence_complete=True) == "NOT_ASSESSABLE"


def test_persistence_uses_only_explicitly_comparable_runs() -> None:
    qualified = persistence_sequence(["WARNING", "WARNING", "NORMAL"], [True, True, True])
    assert qualified[0]["consecutive_breach_count"] == 1
    assert qualified[1]["repeat_breach_escalated"] is True
    assert qualified[2]["consecutive_breach_count"] == 0
    not_comparable = persistence_sequence(["WARNING", "WARNING"], [False, False])
    assert all(row["persistence_status"] == "NOT_ASSESSABLE" for row in not_comparable)


def test_alert_lifecycle_allows_only_governed_forward_transitions() -> None:
    assert transition_alert_status("OPEN", "ACKNOWLEDGED") == "ACKNOWLEDGED"
    assert transition_alert_status("ACKNOWLEDGED", "RESOLVED") == "RESOLVED"
    for current, target in [("OPEN", "RESOLVED"), ("ACKNOWLEDGED", "OPEN"), ("RESOLVED", "OPEN")]:
        try:
            transition_alert_status(current, target)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Invalid lifecycle transition passed: {current} -> {target}")


def test_phase11_candidate_review_gate_when_present() -> None:
    root = Path(__file__).resolve().parents[2]
    report = root / "reports/monitoring/ALERT-ENGINE-01"
    if report.exists():
        decision = json.loads((report / "phase11_completion_decision.json").read_text(encoding="utf-8"))
        assert decision["technical_qualification"] == "PASS"
        assert decision["review_decision"] == "PENDING_USER_PROTOCOL_OWNER_REVIEW"
        assert decision["phase_11_complete"] is False
        assert decision["phase_12_authorized"] is False
        assert decision["overall_model_health_calculated"] is True
        scope = json.loads((report / "scope_protection_attestation.json").read_text(encoding="utf-8"))
        assert scope["new_monitoring_metrics_calculated"] is False
        assert scope["threshold_boundary_density_status"] == "CONTROLLED_DEFERRED"
        assert scope["current_scenario_calendar_persistence_claimed"] is False
