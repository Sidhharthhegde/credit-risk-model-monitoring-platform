from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from credit_risk_monitoring.history.digest import semantic_database_manifest
from credit_risk_monitoring.history.ingest import (
    HistoryIngestor,
    SourceConflictError,
    SourceVerificationError,
    verify_frozen_sources,
)
from credit_risk_monitoring.history.lifecycle import AlertLifecycleService
from credit_risk_monitoring.history.queries import HistoryRepository
from credit_risk_monitoring.history.schema import qualify_schema
from credit_risk_monitoring.history.store import connect_history, table_count
from credit_risk_monitoring.qualification.binding import sha256_file


@pytest.fixture(scope="module")
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def materialized_db(project_root: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("history") / "history.db"
    result = HistoryIngestor(project_root, path).ingest()
    assert result.status == "MATERIALIZED"
    return path


def test_exact_ingestion_counts_and_idempotency(project_root: Path, materialized_db: Path) -> None:
    result = HistoryIngestor(project_root, materialized_db).ingest()
    assert result.status == "IDEMPOTENT_NO_OP" and result.inserted_rows == 0
    assert result.table_counts["monitoring_runs"] == 8
    assert result.table_counts["metric_evidence"] == 2259
    assert result.table_counts["alerts"] == 329
    assert result.table_counts["alert_events"] == 329
    assert result.table_counts["component_health"] == 56
    assert result.table_counts["run_health"] == 8
    assert result.table_counts["phase_manifests"] == 12


def test_schema_constraints_foreign_keys_and_no_applicant_identifiers(materialized_db: Path) -> None:
    connection = connect_history(materialized_db)
    try:
        qualification = qualify_schema(connection)
        assert qualification["result"] == "PASS"
        assert qualification["applicant_identifier_columns"] == []
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO monitoring_runs(history_run_id,model_id,model_version,development_freeze_id,scenario_id,scenario_artifact_id,authorization_state,evidence_scope,overall_model_health,evidence_type,synthetic_evidence,calendar_interpretation,comparable_longitudinal_run,source_phase11_manifest_sha256,run_fingerprint,source_created_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("BAD", "X", "X", "X", "X", "BAD", "INVALID", "NOT_ASSESSABLE", "NOT_ASSESSABLE", "X", 0, 0, 0, "x", "bad", "x"),
            )
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO alert_events(event_id,alert_id,event_sequence,event_type,from_status,to_status,event_utc,actor_type,actor_label,reason,source) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                ("BAD", "DOES-NOT-EXIST", 1, "CREATED", None, "OPEN", "x", "SYSTEM_IMPORT", "x", "x", "x"),
            )
        connection.rollback()
    finally:
        connection.close()


def test_imported_evidence_is_immutable(materialized_db: Path) -> None:
    connection = connect_history(materialized_db)
    try:
        history_run_id = connection.execute("SELECT history_run_id FROM monitoring_runs LIMIT 1").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError, match="immutable imported evidence"):
            connection.execute("UPDATE monitoring_runs SET scenario_id = ? WHERE history_run_id = ?", ("CHANGED", history_run_id))
        connection.rollback()
    finally:
        connection.close()


def test_forced_ingestion_failure_rolls_back_all_evidence(project_root: Path, tmp_path: Path) -> None:
    path = tmp_path / "rollback.db"
    with pytest.raises(RuntimeError, match="QUALIFICATION_FORCED_TRANSACTION_FAILURE"):
        HistoryIngestor(project_root, path).ingest(fail_after_records=50)
    connection = connect_history(path)
    try:
        assert all(table_count(connection, table) == 0 for table in [
            "schema_metadata", "phase_manifests", "monitoring_runs", "metric_evidence", "alerts",
            "alert_events", "component_health", "run_health", "artifact_lineage",
        ])
    finally:
        connection.close()


def test_same_identity_different_contract_content_fails_closed(project_root: Path, materialized_db: Path, tmp_path: Path) -> None:
    copied_contract = tmp_path / "contract.json"
    copied_contract.write_text(
        (project_root / "contracts/monitoring_history_contract.json").read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SourceConflictError, match="HARD_FAIL_SOURCE_CONFLICT"):
        HistoryIngestor(project_root, materialized_db, copied_contract).ingest()


def test_mutated_source_hash_aborts_before_write(project_root: Path, tmp_path: Path) -> None:
    original = project_root / "reports/monitoring/ALERT-ENGINE-01/authorization_results.json"
    mutated = tmp_path / "authorization_results.json"
    mutated.write_bytes(original.read_bytes() + b" ")
    schema = project_root / "schemas/monitoring_history_schema.sql"
    contract = {
        "schema": {
            "schema_path": str(schema), "schema_sha256": sha256_file(schema),
            "migration_path": str(schema), "migration_sha256": sha256_file(schema),
        },
        "phase_manifests": [],
        "phase11_sources": {"authorization": {"path": str(mutated), "sha256": sha256_file(original)}},
    }
    with pytest.raises(SourceVerificationError, match="Frozen Phase 11 source changed"):
        verify_frozen_sources(project_root, contract)


def test_clean_rebuild_has_identical_semantic_digest(project_root: Path, materialized_db: Path, tmp_path: Path) -> None:
    rebuilt = tmp_path / "rebuilt.db"
    rebuilt_result = HistoryIngestor(project_root, rebuilt).ingest()
    first = connect_history(materialized_db, read_only=True)
    second = connect_history(rebuilt, read_only=True)
    try:
        assert semantic_database_manifest(first) == semantic_database_manifest(second)
        assert rebuilt_result.semantic_manifest["physical_database_hash_is_authoritative"] is False
    finally:
        first.close(); second.close()


def test_query_layer_reconciles_alert_health_lineage_and_synthetic_scope(materialized_db: Path) -> None:
    connection = connect_history(materialized_db, read_only=True)
    try:
        repository = HistoryRepository(connection)
        assert len(repository.list_runs()) == 8
        assert len(repository.list_alerts()) == 329
        assert len(repository.list_alerts(status="OPEN")) == 329
        assert len(repository.get_open_critical_alerts()) == 26
        assert len(repository.list_alerts(component="FEATURE_DRIFT")) == 45
        assert {row["authorization_state"] for row in repository.list_blocked_runs()} == {"BLOCKED_HARD_GATE", "BLOCKED_SOURCE_GOVERNANCE"}
        synthetic = repository.get_synthetic_performance_runs()
        assert len(synthetic) == 1 and synthetic[0]["scenario_id"] == "SIM-M06"
        gini = repository.get_metric_evidence(metric_id="gini")
        assert gini and all(row["metric_role"] == "DERIVED_ONLY" for row in gini)
        assert repository.get_evidence_lineage(gini[0]["metric_record_id"])
    finally:
        connection.close()


def test_current_scenarios_cannot_appear_as_longitudinal_history(materialized_db: Path) -> None:
    connection = connect_history(materialized_db, read_only=True)
    try:
        repository = HistoryRepository(connection)
        assert all(row["calendar_interpretation"] == 0 for row in repository.list_runs())
        assert all(row["comparable_longitudinal_run"] == 0 for row in repository.list_runs())
        assert repository.get_comparable_metric_history("feature_psi") == []
    finally:
        connection.close()


def test_lifecycle_ledger_uses_fixture_copy_and_rejects_backward_transition(materialized_db: Path, tmp_path: Path) -> None:
    fixture = tmp_path / "lifecycle.db"
    shutil.copy2(materialized_db, fixture)
    connection = connect_history(fixture)
    try:
        alert_id = connection.execute("SELECT alert_id FROM alerts ORDER BY alert_id LIMIT 1").fetchone()[0]
        service = AlertLifecycleService(connection)
        service.acknowledge_alert(alert_id, "fixture-user", "qualification", event_utc="2030-01-01T00:00:00+00:00")
        service.resolve_alert(alert_id, "fixture-user", "qualification", event_utc="2030-01-01T00:01:00+00:00")
        assert service.current_status(alert_id) == "RESOLVED"
        with pytest.raises(ValueError, match="not permitted"):
            service.acknowledge_alert(alert_id, "fixture-user", "backward", event_utc="2030-01-01T00:02:00+00:00")
        assert [row["to_status"] for row in HistoryRepository(connection).get_alert_history(alert_id)] == ["OPEN", "ACKNOWLEDGED", "RESOLVED"]
    finally:
        connection.close()


def test_history_layer_contains_no_monitoring_recalculation_calls(project_root: Path) -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in (project_root / "src/credit_risk_monitoring/history").glob("*.py"))
    for forbidden in ["predict_proba", "roc_auc_score", "bootstrap", "calculate_psi", "aggregate_health("]:
        assert forbidden not in source


def test_phase12_candidate_gate_when_present(project_root: Path) -> None:
    report = project_root / "reports/persistence/MONITORING-HISTORY-01"
    if report.exists():
        decision = json.loads((report / "phase12_completion_decision.json").read_text(encoding="utf-8"))
        assert decision["technical_qualification"] == "PASS"
        assert decision["review_decision"] == "PENDING_USER_PROTOCOL_OWNER_REVIEW"
        assert decision["phase_12_complete"] is False
        assert decision["phase_13_authorized"] is False
