from __future__ import annotations

import json
import shutil
from pathlib import Path

from credit_risk_monitoring.dashboard.casebook_service import load_casebook
from credit_risk_monitoring.dashboard.data_service import DashboardDataService
from credit_risk_monitoring.dashboard.pages.investigation import _operational_state_changes, _queue_navigation_state
from credit_risk_monitoring.history.digest import semantic_database_manifest
from credit_risk_monitoring.history.store import connect_history
from credit_risk_monitoring.investigation.casebook import build_investigation_casebook
from credit_risk_monitoring.qualification.binding import sha256_file


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "reports/investigation/INVESTIGATION-CASEBOOK-01"


def _case(case_id: str) -> dict:
    return json.loads((OUTPUT / f"{case_id}.json").read_text(encoding="utf-8"))


def test_casebook_contract_and_manifest_are_bound() -> None:
    contract = json.loads((ROOT / "contracts/model_risk_investigation_contract.json").read_text(encoding="utf-8"))
    assert contract["control_id"] == "INVESTIGATION-CASEBOOK-01"
    assert contract["authority_model"]["monitoring_calculation_authority"] is False
    assert contract["authority_model"]["phase_0_through_14_read_only"] is True
    assert contract["authority_model"]["investigation_assessment_authority"] == "APPROVED_AUTHORITATIVE_INVESTIGATION_RECORD"
    assert sha256_file(OUTPUT / "manifest.json") == (OUTPUT / "manifest.sha256").read_text(encoding="utf-8").strip()


def test_approved_casebook_rebuild_is_digest_stable() -> None:
    first = build_investigation_casebook(ROOT)
    second = build_investigation_casebook(ROOT)
    assert first == second


def test_casebook_contains_exactly_four_consolidated_cases() -> None:
    bundle = load_casebook(ROOT)
    assert bundle.registry["case_count"] == 4
    assert [case["case_id"] for case in bundle.cases] == ["INV-01", "INV-02", "INV-03", "INV-04"]
    assert sum(case["source_evidence"]["linked_alert_count"] for case in bundle.cases) == 21
    assert all(case["investigation_assessment"]["owner_review_status"] == "APPROVED" for case in bundle.cases)


def test_primary_evidence_is_governed_by_and_reconciles_inside_each_case() -> None:
    bundle = load_casebook(ROOT)
    for case in bundle.cases:
        primary = case["primary_evidence"]
        linked = case["source_evidence"]["linked_alerts"]
        reconciled = next(row for row in linked if row["alert_id"] == primary["alert_id"])
        assert primary == reconciled
        assert primary["lineage_reference"]["source_record_key"]
        assert primary["metric_id"] and primary["entity_id"]
    qualification = json.loads((OUTPUT / "primary_evidence_reconciliation.json").read_text(encoding="utf-8"))
    assert qualification["selection_authority"] == "APPROVED_CASE_ARTIFACT"
    assert qualification["presentation_layer_selection_permitted"] is False
    assert qualification["result"] == "PASS"


def test_dual_phase12_digest_binding_reconciles_to_current_extraction_state() -> None:
    case = _case("INV-02")
    contract = json.loads((ROOT / "contracts/model_risk_investigation_contract.json").read_text(encoding="utf-8"))
    connection = connect_history(ROOT / contract["frozen_bindings"]["phase12_database_path"], read_only=True)
    try:
        semantic = semantic_database_manifest(connection)
    finally:
        connection.close()
    as_of = case["evidence_as_of"]
    assert as_of["phase12_immutable_evidence_semantic_sha256"] == semantic["immutable_evidence_semantic_sha256"]
    assert as_of["phase12_operational_database_semantic_sha256_at_extraction"] == semantic["database_semantic_sha256"]
    assert as_of["phase15_pre_casebook_candidate_manifest_sha256"] == "096665d8bcb12bd8efcfeb952330e65b5508ce6ea7e035bbf283fe70b45f7fc4"


def test_m04_case_reconciles_exact_governed_values_without_performance_claim() -> None:
    case = _case("INV-02")
    values = {(row["metric_id"], row["entity_id"]): row["metric_value"] for row in case["source_evidence"]["linked_alerts"]}
    assert values[("feature_psi", "EXT_SOURCE_2")] == 0.46145175839108366
    assert values[("feature_psi", "EXT_SOURCE_3")] == 0.25012754553854843
    assert values[("risk_positive_rate_absolute_change", "THRESHOLD-01")] == 0.0883799909049509
    assert "performance impact cannot be determined" in case["investigation_assessment"]["executive_finding"]


def test_m06_synthetic_classification_is_permanent_and_non_empirical() -> None:
    case = _case("INV-03")
    limitations = set(case["investigation_assessment"]["evidence_limitations"])
    assert {"SYNTHETIC_SCENARIO_EVIDENCE", "NON_EMPIRICAL", "NOT_EXTERNAL_VALIDATION"} <= limitations
    assert case["investigation_assessment"]["model_defect_established"] == "NOT_ASSESSABLE"
    assert case["scope_assertions"]["production_inference_claimed"] is False


def test_m05_three_state_semantics_preserve_governance_blocks() -> None:
    case = _case("INV-04")
    contexts = {row["scenario_artifact_id"]: row for row in case["case_context"]["scenarios"]}
    assert contexts["SIM-M05-VALID-DEGRADED-01"]["authorization_state"] == "AUTHORIZED"
    assert contexts["SIM-M05-SOURCE-LOSS-DIAGNOSTIC-01"]["overall_health"] == "NOT_ASSESSABLE"
    assert contexts["SIM-M05-HARD-FAIL-01"]["overall_health"] == "NOT_ASSESSABLE"
    comparison = case["investigation_assessment"]["control_state_comparison"]
    assert len(comparison) == 3
    assert comparison[1]["technical_scoring"] == "PASS"
    assert comparison[1]["governance_authorization"] == "BLOCKED_SOURCE_GOVERNANCE"
    assert comparison[2]["governance_authorization"] == "BLOCKED_HARD_GATE"


def test_assessment_does_not_mutate_or_masquerade_as_source_evidence() -> None:
    qualification = json.loads((OUTPUT / "scope_protection_attestation.json").read_text(encoding="utf-8"))
    assert qualification["phase_0_through_14_artifact_hashes_unchanged"] is True
    assert qualification["database_semantic_manifest_unchanged_during_extraction"] is True
    assert qualification["alert_event_ledger_unchanged"] is True
    for case_id in ("INV-01", "INV-02", "INV-03", "INV-04"):
        case = _case(case_id)
        assert case["source_evidence"]["authority"] == "FROZEN_MONITORING_EVIDENCE"
        assert case["investigation_assessment"]["authority"] == "APPROVED_AUTHORITATIVE_INVESTIGATION_RECORD"
        assert case["investigation_assessment"]["remediation_status"] == "NOT_CLAIMED"
        narrative = json.dumps(case["investigation_assessment"])
        assert all(token not in narrative for token in ("FAIRNESS_CERTIFIED", "BIAS_FREE", "NO_DISPARITY", "RESPONSIBLE_AI_APPROVED"))


def test_casebook_builder_has_no_monitoring_calculation_or_scoring_dependencies() -> None:
    source = (ROOT / "src/credit_risk_monitoring/investigation/casebook.py").read_text(encoding="utf-8")
    forbidden = (
        "credit_risk_monitoring.alert.engine", "credit_risk_monitoring.data_quality.engine",
        "credit_risk_monitoring.drift.engine", "credit_risk_monitoring.outcome.engine",
        "credit_risk_monitoring.prediction.engine", "predict_proba", "roc_auc_score", "calculate_psi",
    )
    assert all(token not in source for token in forbidden)


def test_frozen_extraction_status_does_not_hide_alert_after_current_lifecycle_change(tmp_path: Path) -> None:
    bundle = load_casebook(ROOT)
    case = next(row for row in bundle.cases if row["case_id"] == "INV-04")
    primary = case["primary_evidence"]
    assert primary["alert_status_at_extraction"] == "OPEN"

    source_db = ROOT / "artifacts/monitoring_history/MONITORING-HISTORY-01/monitoring_history.db"
    fixture = tmp_path / "casebook-current-state.db"
    shutil.copy2(source_db, fixture)
    with DashboardDataService(ROOT, fixture, writable=True) as service:
        service.acknowledge(
            primary["alert_id"], "LOCAL_DEMO_USER", "casebook temporal navigation fixture", confirmed=True
        )

    with DashboardDataService(ROOT, fixture) as service:
        current = next(row for row in service.alerts() if row.alert_id == primary["alert_id"])
        assert current.current_status == "ACKNOWLEDGED"
        navigation = _queue_navigation_state(primary, "SIM-M05")
        assert navigation["alert_status"] == "All"
        assert navigation["alert_dossier"] == primary["alert_id"]
        queue = service.alerts(
            severity=navigation["alert_severity"], status=None,
            component=navigation["alert_component"], scenario_id=navigation["alert_scenario"],
        )
        linked = next(row for row in queue if row.alert_id == navigation["alert_dossier"])
        assert linked.current_status == "ACKNOWLEDGED"
        changes = _operational_state_changes(case, service.alerts())
        assert {"alert_id": primary["alert_id"], "at_extraction": "OPEN", "current": "ACKNOWLEDGED"} in changes
