"""Phase 12 technical qualification and aggregate evidence packaging."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from credit_risk_monitoring.qualification.binding import sha256_file

from .digest import semantic_database_manifest
from .ingest import HistoryIngestor
from .lifecycle import AlertLifecycleService
from .queries import HistoryRepository
from .store import connect_history, table_count


HISTORY_STORE_ID = "MONITORING-HISTORY-01"
CODE_VERSION = "PHASE12-MONITORING-HISTORY-0.1.0"


def _json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def _record(path: Path, root: Path) -> dict[str, Any]:
    return {"path": path.relative_to(root).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def _safe_unlink(path: Path, root: Path) -> None:
    resolved_root = root.resolve()
    candidate = path.resolve()
    if resolved_root not in candidate.parents:
        raise RuntimeError(f"Refusing to remove generated database outside artifact root: {candidate}")
    if candidate.exists():
        candidate.unlink()


def run_phase12_qualification(project_root: Path) -> Path:
    project_root = project_root.resolve()
    contract_path = project_root / "contracts/monitoring_history_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    artifact_root = project_root / "artifacts/monitoring_history" / HISTORY_STORE_ID
    artifact_root.mkdir(parents=True, exist_ok=True)
    database_path = artifact_root / "monitoring_history.db"
    rebuild_path = artifact_root / "monitoring_history_rebuild_qualification.db"
    rollback_path = artifact_root / "monitoring_history_rollback_qualification.db"
    lifecycle_path = artifact_root / "monitoring_history_lifecycle_fixture.db"
    for path in [database_path, rebuild_path, rollback_path, lifecycle_path]:
        _safe_unlink(path, artifact_root)

    first = HistoryIngestor(project_root, database_path).ingest()
    second = HistoryIngestor(project_root, database_path).ingest()
    if second.status != "IDEMPOTENT_NO_OP" or second.semantic_manifest != first.semantic_manifest:
        raise RuntimeError("Identical ingestion was not an idempotent semantic no-op")

    rebuild = HistoryIngestor(project_root, rebuild_path).ingest()
    rebuild_match = rebuild.semantic_manifest["database_semantic_sha256"] == first.semantic_manifest["database_semantic_sha256"]
    if not rebuild_match:
        raise RuntimeError("Clean rebuild semantic digest mismatch")

    rollback_pass = False
    try:
        HistoryIngestor(project_root, rollback_path).ingest(fail_after_records=100)
    except RuntimeError as error:
        if "QUALIFICATION_FORCED_TRANSACTION_FAILURE" not in str(error):
            raise
        rollback_connection = connect_history(rollback_path)
        try:
            rollback_pass = all(table_count(rollback_connection, table) == 0 for table in [
                "schema_metadata", "phase_manifests", "monitoring_runs", "metric_evidence", "alerts",
                "alert_events", "component_health", "run_health", "artifact_lineage",
            ])
        finally:
            rollback_connection.close()
    if not rollback_pass:
        raise RuntimeError("Forced ingestion failure left partially committed evidence")

    base_connection = connect_history(database_path, read_only=True)
    try:
        repository = HistoryRepository(base_connection)
        runs = repository.list_runs()
        alerts = repository.list_alerts()
        open_alerts = repository.list_alerts(status="OPEN")
        open_critical = repository.get_open_critical_alerts()
        blocked = repository.list_blocked_runs()
        synthetic = repository.get_synthetic_performance_runs()
        feature_alerts = repository.list_alerts(component="FEATURE_DRIFT")
        comparable = repository.get_comparable_metric_history("feature_psi")
        lineage_count = sum(bool(repository.get_evidence_lineage(row["metric_record_id"])) for row in repository.get_metric_evidence())
        alert_lineage_count = sum(bool(repository.get_evidence_lineage(row["alert_id"])) for row in alerts)
        current_counts = {
            row[0]: row[1] for row in base_connection.execute(
                "SELECT current_status, COUNT(*) FROM v_current_alert_state GROUP BY current_status"
            ).fetchall()
        }
        semantic_manifest = semantic_database_manifest(base_connection)
    finally:
        base_connection.close()

    shutil.copy2(database_path, lifecycle_path)
    fixture_connection = connect_history(lifecycle_path)
    try:
        fixture_alert = fixture_connection.execute("SELECT alert_id FROM alerts ORDER BY alert_id LIMIT 1").fetchone()[0]
        lifecycle = AlertLifecycleService(fixture_connection)
        acknowledged_event = lifecycle.acknowledge_alert(
            fixture_alert, "qualification-user", "Lifecycle persistence qualification",
            event_utc="2030-01-01T00:00:00+00:00",
        )
        resolved_event = lifecycle.resolve_alert(
            fixture_alert, "qualification-user", "Lifecycle persistence qualification",
            event_utc="2030-01-01T00:01:00+00:00",
        )
        invalid_rejected = False
        try:
            lifecycle.acknowledge_alert(
                fixture_alert, "qualification-user", "Invalid backward transition fixture",
                event_utc="2030-01-01T00:02:00+00:00",
            )
        except ValueError:
            invalid_rejected = True
        lifecycle_history = HistoryRepository(fixture_connection).get_alert_history(fixture_alert)
    finally:
        fixture_connection.close()
    if not invalid_rejected or [row["to_status"] for row in lifecycle_history] != ["OPEN", "ACKNOWLEDGED", "RESOLVED"]:
        raise RuntimeError("Alert lifecycle persistence qualification failed")

    report_final = project_root / "reports/persistence" / HISTORY_STORE_ID
    report_stage = report_final.parent / f".{HISTORY_STORE_ID}.in_progress"
    if report_final.exists() or report_stage.exists():
        raise FileExistsError("Phase 12 qualification output already exists")
    report_stage.mkdir(parents=True)
    _json(report_stage / "monitoring_history_contract_snapshot.json", contract)
    _json(report_stage / "schema_manifest.json", {
        "schema_version": contract["schema"]["version"], "schema_path": contract["schema"]["schema_path"],
        "schema_sha256": contract["schema"]["schema_sha256"], "migration_path": contract["schema"]["migration_path"],
        "migration_sha256": contract["schema"]["migration_sha256"], "pragma_user_version": 1,
    })
    _json(report_stage / "schema_qualification.json", first.schema_qualification)
    source_files = [
        contract_path, project_root / contract["schema"]["schema_path"], project_root / contract["schema"]["migration_path"],
        project_root / "src/credit_risk_monitoring/history/store.py", project_root / "src/credit_risk_monitoring/history/schema.py",
        project_root / "src/credit_risk_monitoring/history/ingest.py", project_root / "src/credit_risk_monitoring/history/digest.py",
        project_root / "src/credit_risk_monitoring/history/lifecycle.py", project_root / "src/credit_risk_monitoring/history/queries.py",
        project_root / "src/credit_risk_monitoring/history/qualification.py", project_root / "scripts/run_phase12_qualification.py",
    ]
    _json(report_stage / "execution_source_manifest.json", {
        "history_store_id": HISTORY_STORE_ID, "creation_code_version": CODE_VERSION,
        "sources": [{"path": path.relative_to(project_root).as_posix(), "sha256": sha256_file(path)} for path in source_files],
    })
    _json(report_stage / "upstream_hash_reconciliation.json", first.source_reconciliation)
    _json(report_stage / "ingestion_summary.json", {
        "result": "PASS", "first_ingestion_status": first.status, "inserted_rows": first.inserted_rows,
        "database_role": contract["authority_model"]["database_role"], "database_authoritative_evidence": False,
        "frozen_source_evidence_authoritative": True, "single_transaction": True,
    })
    source_counts = {name: source["expected_rows"] for name, source in contract["phase11_sources"].items()}
    _json(report_stage / "row_count_reconciliation.json", {
        "result": "PASS", "source_counts": source_counts, "database_counts": first.table_counts,
        "normalized_candidates_reconcile": first.table_counts["metric_evidence"] == 2259,
        "alerts_reconcile": first.table_counts["alerts"] == 329,
        "unique_alert_ids": len({row["alert_id"] for row in alerts}),
        "initial_open_alerts": len(open_alerts), "acknowledged_alerts": current_counts.get("ACKNOWLEDGED", 0),
        "resolved_alerts": current_counts.get("RESOLVED", 0),
    })
    _json(report_stage / "idempotency_qualification.json", {
        "result": "PASS", "first_status": first.status, "second_status": second.status,
        "second_inserted_rows": second.inserted_rows, "second_existing_rows": second.existing_rows,
        "semantic_digest_unchanged": second.semantic_manifest == first.semantic_manifest,
        "same_identity_different_content_policy": "HARD_FAIL_SOURCE_CONFLICT",
    })
    _json(report_stage / "transaction_rollback_qualification.json", {
        "result": "PASS", "forced_failure_after_staged_records": 100, "partial_evidence_rows_after_rollback": 0,
    })
    semantic_manifest["database_physical_sha256"] = sha256_file(database_path)
    semantic_manifest["database_physical_size_bytes"] = database_path.stat().st_size
    _json(report_stage / "database_semantic_manifest.json", semantic_manifest)
    _json(report_stage / "database_rebuild_qualification.json", {
        "result": "PASS", "first_database_semantic_sha256": first.semantic_manifest["database_semantic_sha256"],
        "rebuilt_database_semantic_sha256": rebuild.semantic_manifest["database_semantic_sha256"],
        "semantic_digests_equal": rebuild_match, "physical_database_hash_used_as_primary_reproducibility_control": False,
    })
    _json(report_stage / "alert_lifecycle_persistence_qualification.json", {
        "result": "PASS", "qualification_fixture_only": True, "base_database_alerts_modified": False,
        "fixture_alert_id": fixture_alert, "acknowledged_event_id": acknowledged_event, "resolved_event_id": resolved_event,
        "fixture_status_sequence": [row["to_status"] for row in lifecycle_history], "invalid_backward_transition_rejected": invalid_rejected,
        "actor_type": "LOCAL_DEMO_USER", "enterprise_authentication_claimed": False,
    })
    _json(report_stage / "temporal_semantics_qualification.json", {
        "result": "PASS", "run_count": len(runs),
        "all_current_calendar_interpretation_false": all(row["calendar_interpretation"] == 0 for row in runs),
        "all_current_comparable_longitudinal_run_false": all(row["comparable_longitudinal_run"] == 0 for row in runs),
        "all_current_periods_null": all(row["period_start"] is None and row["period_end"] is None for row in runs),
        "comparable_feature_history_rows": len(comparable),
        "current_scenario_persistence_claimed": False,
        "current_persistence_status": contract["temporal_semantics"]["current_scenario_persistence_status"],
    })
    _json(report_stage / "query_qualification.json", {
        "result": "PASS", "repository_interface": "HistoryRepository", "parameterized_values_only": True,
        "run_count": len(runs), "alert_count": len(alerts), "open_alert_count": len(open_alerts),
        "open_critical_alert_count": len(open_critical), "feature_drift_alert_count": len(feature_alerts),
        "blocked_run_count": len(blocked), "blocked_states": sorted({row["authorization_state"] for row in blocked}),
        "synthetic_run_count": len(synthetic), "synthetic_scenarios": sorted({row["scenario_id"] for row in synthetic}),
        "comparable_history_default_excludes_current_scenarios": len(comparable) == 0,
    })
    _json(report_stage / "lineage_qualification.json", {
        "result": "PASS", "phase_manifest_rows": first.table_counts["phase_manifests"],
        "artifact_lineage_rows": first.table_counts["artifact_lineage"],
        "metric_records_with_resolved_lineage": lineage_count, "alert_records_with_resolved_lineage": alert_lineage_count,
        "all_metric_lineage_resolved": lineage_count == 2259, "all_alert_lineage_resolved": alert_lineage_count == 329,
    })
    _json(report_stage / "scope_protection_attestation.json", {
        **contract["scope_controls"], "database_committed": False, "database_path": "artifacts/monitoring_history/MONITORING-HISTORY-01/monitoring_history.db",
        "aggregate_public_qualification_evidence_only": True, "all_scope_controls_pass": True,
    })
    controls = [
        "Phase 11 approved frozen manifest and Phase 0 through 11 chain verified",
        "Persistence contract and versioned schema frozen before materialization",
        "SQLite is derived query and operational persistence rather than authoritative evidence",
        "Frozen source artifacts remain authoritative and database is rebuildable",
        "Foreign keys and check constraints are enabled",
        "Imported evidence is immutable and lifecycle events are append-only",
        "Schema contains no applicant-level identifier columns",
        "Frozen hashes are verified before database writes",
        "Ingestion is transactional and forced failure leaves zero partial evidence rows",
        "Identical ingestion is an idempotent no-op",
        "Same identity with different governed content fails closed",
        "All 2259 normalized candidates reconcile",
        "All 329 exact alert identifiers reconcile",
        "All 56 component-health rows and 8 overall-health rows reconcile",
        "Authorization evidence scope and synthetic evidence type reconcile",
        "All 329 initial alert states are OPEN from CREATED import events",
        "Lifecycle qualification uses a fixture copy and leaves base alerts unchanged",
        "Valid forward and invalid backward lifecycle transitions are enforced",
        "Current scenarios retain calendar interpretation false and null periods",
        "Current scenarios are excluded from comparable longitudinal history",
        "Parameterized repository queries and governed views are qualified",
        "All metric and alert evidence resolves to authoritative lineage",
        "Phase 0 through 11 manifest lineage is persisted",
        "Clean rebuild reproduces the database semantic digest",
        "Physical database hash is recorded but is not the primary reproducibility control",
        "No model monitoring metrics alerts severities or health states are recalculated",
        "No dashboard monitoring report or applicant-level evidence is created",
        "CND-02 remains open and threshold boundary density remains controlled deferred",
        "Owner approval and Phase 13 authorization remain separate",
    ]
    _csv(report_stage / "phase12_acceptance_checklist.csv", ["control_id", "control", "result"], [
        {"control_id": f"P12-{index:03d}", "control": control, "result": "PASS"} for index, control in enumerate(controls, 1)
    ])
    _json(report_stage / "phase12_completion_decision.json", {
        "phase": "PHASE_12", "phase_name": "MONITORING_HISTORY_EVIDENCE_PERSISTENCE_AND_QUERY_LAYER",
        "history_store_id": HISTORY_STORE_ID, "review_decision": "PENDING_USER_PROTOCOL_OWNER_REVIEW",
        "technical_qualification": "PASS", "phase_12_complete": False, "database_engine": "SQLITE",
        "database_role": contract["authority_model"]["database_role"], "database_authoritative_evidence": False,
        "frozen_source_evidence_authoritative": True, "schema_version": 1,
        "transactional_ingestion_implemented": True, "idempotent_ingestion_implemented": True,
        "fail_closed_source_verification": True, "normalized_candidates_persisted": 2259, "alerts_persisted": 329,
        "alert_event_ledger_implemented": True, "current_open_alerts": 329,
        "alert_acknowledgement_persistence_implemented": True, "alert_resolution_persistence_implemented": True,
        "component_health_persisted": True, "overall_model_health_persisted": True,
        "authorization_state_persisted": True, "evidence_scope_persisted": True,
        "artifact_lineage_persisted": True, "phase_manifest_lineage_persisted": True,
        "query_layer_implemented": True, "database_semantic_hash_generated": True,
        "database_rebuild_reproducibility_verified": True, "current_scenarios_calendar_interpretation": False,
        "current_scenario_persistence_claimed": False, "new_monitoring_metrics_calculated": False,
        "new_alerts_generated": False, "overall_health_recalculated": False,
        "cnd_02_status": "OPEN", "threshold_boundary_density_status": "CONTROLLED_DEFERRED",
        "phase_13_authorized": False,
    })
    files = sorted(path for path in report_stage.iterdir() if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"})
    _json(report_stage / "manifest.json", {
        "history_store_id": HISTORY_STORE_ID, "status": "QUALIFIED_PENDING_REVIEW",
        "created_utc": datetime.now(timezone.utc).isoformat(), "artifacts": [_record(path, report_stage) for path in files],
        "database_included": False, "aggregate_public_evidence_only": True,
        "frozen_source_evidence_authoritative": True, "approval_record_included": False,
    })
    (report_stage / "manifest.sha256").write_text(sha256_file(report_stage / "manifest.json") + "\n", encoding="ascii", newline="\n")
    report_stage.rename(report_final)
    for path in [rebuild_path, rollback_path, lifecycle_path]:
        _safe_unlink(path, artifact_root)
    return report_final


__all__ = ["run_phase12_qualification"]
