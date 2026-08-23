from __future__ import annotations

import json
from pathlib import Path

import pytest
from pypdf import PdfReader

from credit_risk_monitoring.orchestration.gates import (
    FrozenEvidenceWriteError,
    guard_output_path,
    outcome_stage_status,
    scoring_gate,
)
from credit_risk_monitoring.orchestration.replay import isolated_semantic_replay, remove_replay_output
from credit_risk_monitoring.orchestration.runner import MonitoringOrchestrator
from credit_risk_monitoring.orchestration.stages import STAGE_REGISTRY
from credit_risk_monitoring.qualification.binding import sha256_file


@pytest.fixture(scope="module")
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def contract(project_root: Path) -> dict:
    return json.loads((project_root / "contracts/final_lifecycle_qualification_contract.json").read_text(encoding="utf-8"))


def test_phase_0_through_13_manifest_chain_is_exact(project_root: Path, contract: dict) -> None:
    assert len(contract["phase_manifest_chain"]) == 14
    assert all(sha256_file(project_root / item["path"]) == item["sha256"] for item in contract["phase_manifest_chain"])


def test_stage_registry_is_ordered_and_report_follows_health() -> None:
    assert [order for _, order in STAGE_REGISTRY] == list(range(14))
    names = [name for name, _ in STAGE_REGISTRY]
    assert names.index("MONITORING_REPORT") > names.index("ALERT_HEALTH_AGGREGATION")
    assert names.index("DATA_QUALITY_SOURCE_AUTHORITY") < names.index("PREDICTION")


def test_hard_and_source_governance_gates_remain_distinct() -> None:
    hard = scoring_gate(hard_fail=True, source_authorized=True)
    source = scoring_gate(hard_fail=False, source_authorized=False)
    assert hard == {"technical_scoring": False, "authoritative_use": False, "state": "BLOCKED_HARD_GATE"}
    assert source == {"technical_scoring": True, "authoritative_use": False, "state": "BLOCKED_SOURCE_GOVERNANCE"}


def test_outcome_gate_preserves_not_assessable_and_synthetic_scope() -> None:
    assert outcome_stage_status(outcomes_available=False, synthetic=False) == "SKIPPED_NOT_ASSESSABLE_OUTCOME_NOT_AVAILABLE"
    assert outcome_stage_status(outcomes_available=True, synthetic=True) == "EXECUTED_SYNTHETIC_SCENARIO_EVIDENCE"


def test_frozen_output_write_attempt_fails_closed(project_root: Path, contract: dict) -> None:
    target = project_root / "reports/monitoring/FEATURE-DRIFT-MONITORING-01/forbidden.json"
    with pytest.raises(FrozenEvidenceWriteError, match="HARD_FAIL_FROZEN_EVIDENCE_WRITE_ATTEMPT"):
        guard_output_path(project_root, target, contract["frozen_write_roots"], contract["permitted_phase14_write_roots"])


def test_phase14_output_roots_are_permitted(project_root: Path, contract: dict) -> None:
    guard_output_path(project_root, project_root / "reports/lifecycle/FUTURE", contract["frozen_write_roots"], contract["permitted_phase14_write_roots"])


def test_verify_frozen_mode_is_non_mutating_and_passes(project_root: Path) -> None:
    result = MonitoringOrchestrator(project_root).verify_frozen(generate_report=False)
    assert result.mode == "VERIFY_FROZEN" and result.status == "PASS"
    assert result.output_root is None and len(result.stages) == 14


def test_isolated_semantic_replay_rebuilds_phase12(project_root: Path, contract: dict, tmp_path: Path) -> None:
    output = tmp_path / "approved" / "replay"
    payload = isolated_semantic_replay(project_root, output, contract)
    assert payload["result"] == "PASS"
    assert payload["database_semantic_match"] is True
    assert payload["immutable_evidence_semantic_match"] is True
    assert payload["full_upstream_calculation_replay_performed"] is False
    remove_replay_output(output, tmp_path / "approved")


def test_report_snapshot_and_outputs_reconcile(project_root: Path) -> None:
    report = project_root / "reports/monitoring_report/MONITORING-REPORT-01"
    snapshot = json.loads((report / "monitoring_report_snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["counts"]["metrics"] == 2259
    assert snapshot["counts"]["alerts"] == 329
    assert snapshot["counts"]["current_open_critical"] == 26
    assert snapshot["counts"]["comparable_history_rows"] == 0
    assert (report / "monitoring_report.html").is_file()
    assert len(PdfReader(report / "monitoring_report.pdf").pages) == 2


def test_report_preserves_synthetic_and_nonproduction_disclosures(project_root: Path) -> None:
    report = project_root / "reports/monitoring_report/MONITORING-REPORT-01"
    html = (report / "monitoring_report.html").read_text(encoding="utf-8")
    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(report / "monitoring_report.pdf").pages)
    for disclosure in ["production deployment", "not external validation", "cnd-02", "controlled_deferred"]:
        assert disclosure in html.lower() and disclosure in pdf_text.lower()


def test_report_and_orchestration_do_not_call_monitoring_engines(project_root: Path) -> None:
    paths = list((project_root / "src/credit_risk_monitoring/reporting").rglob("*.py"))
    paths += [path for path in (project_root / "src/credit_risk_monitoring/orchestration").rglob("*.py") if path.name != "qualification.py"]
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    for forbidden in ["predict_proba", "roc_auc_score", "calculate_psi", "run_phase6_monitoring", "run_phase7_monitoring", "run_phase8_monitoring", "run_phase9_monitoring", "run_phase10_monitoring", "run_phase11_alert_engine"]:
        assert forbidden not in source


def test_phase14_candidate_gate_when_present(project_root: Path) -> None:
    decision = project_root / "reports/lifecycle/FINAL-LIFECYCLE-QUALIFICATION-01/phase14_completion_decision.json"
    if decision.exists():
        payload = json.loads(decision.read_text(encoding="utf-8"))
        assert payload["technical_qualification"] == "PASS"
        assert payload["review_decision"] == "PENDING_OWNER_REVIEW"
        assert payload["phase_14_complete"] is False
        assert payload["project_implementation_complete"] is False
