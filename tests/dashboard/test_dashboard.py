from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from credit_risk_monitoring.dashboard.data_service import DashboardDataService
from credit_risk_monitoring.dashboard.navigation import PAGE_REGISTRY
from credit_risk_monitoring.history.digest import semantic_database_manifest


@pytest.fixture(scope="module")
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def database_path(project_root: Path) -> Path:
    return project_root / "artifacts/monitoring_history/MONITORING-HISTORY-01/monitoring_history.db"


def test_dashboard_reconciles_frozen_phase12_query_layer(project_root: Path, database_path: Path) -> None:
    with DashboardDataService(project_root, database_path) as service:
        snapshot = service.snapshot()
        assert snapshot.metric_count == 2259
        assert snapshot.alert_count == 329
        assert snapshot.open_alert_count == 329
        assert snapshot.open_critical_count == 26
        assert snapshot.blocked_run_count == 2
        assert snapshot.synthetic_run_count == 1
        assert snapshot.comparable_history_count == 0


def test_six_page_registry_is_frozen() -> None:
    assert [page_id for page_id, _ in PAGE_REGISTRY] == [
        "OVERVIEW", "DATA_QUALITY", "FEATURE_DRIFT", "PREDICTION", "PERFORMANCE", "INVESTIGATION",
    ]


def test_blocked_runs_are_not_rendered_as_critical_health(project_root: Path, database_path: Path) -> None:
    with DashboardDataService(project_root, database_path) as service:
        blocked = [row for row in service.scenarios() if row.authorization != "AUTHORIZED"]
        assert {row.authorization for row in blocked} == {"BLOCKED_HARD_GATE", "BLOCKED_SOURCE_GOVERNANCE"}
        assert all(row.overall_health == "NOT_ASSESSABLE" for row in blocked)


def test_synthetic_scope_and_metric_roles_are_preserved(project_root: Path, database_path: Path) -> None:
    with DashboardDataService(project_root, database_path) as service:
        synthetic = [row for row in service.scenarios() if row.synthetic]
        assert len(synthetic) == 1
        assert synthetic[0].evidence_type == "SYNTHETIC_SCENARIO_EVIDENCE"
        roles = {metric: {row.metric_role for row in service.metrics(metric_id=metric)} for metric in ["roc_auc", "pr_auc_average_precision", "gini"]}
        assert roles["roc_auc"] == {"DIRECT_ALERT_DRIVER"}
        assert roles["pr_auc_average_precision"] == {"SUPPORTING_CORROBORATION"}
        assert roles["gini"] == {"DERIVED_ONLY"}
        disclosure = service.policy["disclosures"]["synthetic"]
        assert "NON-EMPIRICAL" in disclosure and "NOT EXTERNAL VALIDATION" in disclosure


def test_segment_registry_is_context_only_and_disclaims_fairness(project_root: Path, database_path: Path) -> None:
    with DashboardDataService(project_root, database_path) as service:
        registry = service.segment_registry()
        assert registry["family_count"] == 12 and registry["level_count"] == 32
        assert "does not establish fairness" in service.policy["disclosures"]["fairness"]
        assert service.policy["governed_unavailable"]["detailed_segment_results"]


def test_lifecycle_actions_require_confirmation_and_preserve_source_counts(
    project_root: Path, database_path: Path, tmp_path: Path,
) -> None:
    fixture = tmp_path / "dashboard-lifecycle.db"
    shutil.copy2(database_path, fixture)
    with DashboardDataService(project_root, fixture, writable=True) as service:
        alert = service.alerts()[0]
        initial = service.snapshot()
        source_before = sum(row.phase11_source_open for row in service.scenarios())
        with pytest.raises(ValueError, match="confirmation"):
            service.acknowledge(alert.alert_id, "reviewer", "investigation", confirmed=False)
        service.acknowledge(alert.alert_id, "reviewer", "investigation", confirmed=True)
        acknowledged = service.snapshot()
        assert acknowledged.open_alert_count == initial.open_alert_count - 1
        assert sum(row.current_acknowledged for row in acknowledged.scenarios) == 1
        service.resolve(alert.alert_id, "reviewer", "resolved fixture", confirmed=True)
        resolved = service.snapshot()
        assert sum(row.current_acknowledged for row in resolved.scenarios) == 0
        assert sum(row.current_resolved for row in resolved.scenarios) == 1
        assert sum(row.phase11_source_open for row in resolved.scenarios) == source_before
        with pytest.raises(ValueError, match="not permitted"):
            service.acknowledge(alert.alert_id, "reviewer", "backward", confirmed=True)

    # Legitimate ledger writes alter the complete DB digest but not immutable evidence.
    with DashboardDataService(project_root, fixture) as reopened:
        semantic = semantic_database_manifest(reopened.connection)
        contract = json.loads((project_root / "contracts/monitoring_dashboard_contract.json").read_text(encoding="utf-8"))
        binding = contract["frozen_phase12_binding"]
        assert semantic["database_semantic_sha256"] != binding["initial_database_semantic_sha256"]
        assert semantic["immutable_evidence_semantic_sha256"] == binding["immutable_evidence_semantic_sha256"]


def test_dashboard_contains_no_monitoring_recalculation_or_applicant_data(project_root: Path) -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (project_root / "src/credit_risk_monitoring/dashboard").rglob("*.py")
        if path.name != "qualification.py"
    )
    for forbidden in ["predict_proba", "roc_auc_score", "calculate_psi", "aggregate_health(", "SK_ID_CURR", "read_parquet", "reports/monitoring/"]:
        assert forbidden not in source


def test_all_six_streamlit_pages_smoke_without_exceptions(
    project_root: Path, database_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = tmp_path / "dashboard-smoke.db"
    shutil.copy2(database_path, fixture)
    monkeypatch.setenv("CREDIT_RISK_MONITORING_ROOT", str(project_root))
    monkeypatch.setenv("CREDIT_RISK_HISTORY_DB", str(fixture))
    app = AppTest.from_file(str(project_root / "src/credit_risk_monitoring/dashboard/app.py")).run(timeout=60)
    assert not app.exception
    for _, title in PAGE_REGISTRY[1:]:
        app.sidebar.radio[0].set_value(title).run(timeout=60)
        assert not app.exception, title


def test_phase13_candidate_gate_when_present(project_root: Path) -> None:
    decision = project_root / "reports/dashboard/MONITORING-DASHBOARD-01/phase13_completion_decision.json"
    if decision.exists():
        payload = json.loads(decision.read_text(encoding="utf-8"))
        assert payload["technical_qualification"] == "PASS"
        if payload["review_decision"] == "APPROVED":
            assert payload["phase_13_complete"] is True
            assert payload["phase_14_authorized"] is True
        else:
            assert payload["review_decision"] == "PENDING_OWNER_REVIEW"
            assert payload["phase_13_complete"] is False
            assert payload["phase_14_authorized"] is False
