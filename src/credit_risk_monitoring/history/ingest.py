"""Fail-closed deterministic ingestion of frozen Phase 11 evidence."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from credit_risk_monitoring.qualification.binding import sha256_file

from .digest import semantic_database_manifest
from .schema import qualify_schema
from .store import connect_history, initialize_history, table_count


class SourceVerificationError(RuntimeError):
    """Frozen source evidence failed hash, approval, or schema verification."""


class SourceConflictError(RuntimeError):
    """A deterministic identity already exists with different governed content."""


@dataclass(frozen=True)
class IngestionResult:
    status: str
    inserted_rows: int
    existing_rows: int
    table_counts: dict[str, int]
    semantic_manifest: dict[str, Any]
    source_reconciliation: dict[str, Any]
    schema_qualification: dict[str, Any]


def _json_canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _sha(payload: Any) -> str:
    return hashlib.sha256(_json_canonical(payload).encode("utf-8")).hexdigest()


def _value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, bool):
        return int(value)
    return value


def _history_run_id(artifact_id: str) -> str:
    return "HRUN-" + hashlib.sha256(artifact_id.encode("utf-8")).hexdigest()[:24].upper()


def _resolve_manifest_artifact(project_root: Path, manifest_path: Path, relative: str, expected_hash: str) -> Path:
    candidates = [manifest_path.parent / relative, project_root / relative]
    for candidate in candidates:
        if candidate.is_file() and sha256_file(candidate) == expected_hash:
            return candidate.resolve()
    raise SourceVerificationError(f"Manifest artifact missing or changed: {relative}")


def verify_frozen_sources(project_root: Path, contract: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    schema = contract["schema"]
    for path_key, hash_key in [("schema_path", "schema_sha256"), ("migration_path", "migration_sha256")]:
        path = project_root / schema[path_key]
        if sha256_file(path) != schema[hash_key]:
            raise SourceVerificationError(f"Frozen schema dependency changed: {path}")
    lineages: list[dict[str, Any]] = []
    manifest_results = []
    for binding in contract["phase_manifests"]:
        manifest_path = (project_root / binding["path"]).resolve()
        actual = sha256_file(manifest_path)
        if actual != binding["sha256"]:
            raise SourceVerificationError(f"Frozen Phase {binding['phase']} manifest changed")
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if payload.get("status") != "APPROVED_FROZEN":
            raise SourceVerificationError(f"Phase {binding['phase']} is not approved frozen")
        lineages.append({
            "phase": binding["phase"], "artifact_type": "PHASE_MANIFEST",
            "artifact_path": manifest_path.relative_to(project_root).as_posix(), "artifact_sha256": actual,
            "parent_manifest_sha256": actual,
        })
        verified_artifacts = 0
        for artifact in payload.get("artifacts", []):
            resolved = _resolve_manifest_artifact(project_root, manifest_path, artifact["path"], artifact["sha256"])
            lineages.append({
                "phase": binding["phase"], "artifact_type": resolved.suffix.lstrip(".").upper() or "FILE",
                "artifact_path": resolved.relative_to(project_root).as_posix(), "artifact_sha256": artifact["sha256"],
                "parent_manifest_sha256": actual,
            })
            verified_artifacts += 1
        manifest_results.append({"phase": binding["phase"], "manifest_sha256": actual, "artifact_count_verified": verified_artifacts, "result": "PASS"})
    for name, source in contract["phase11_sources"].items():
        path = project_root / source["path"]
        if sha256_file(path) != source["sha256"]:
            raise SourceVerificationError(f"Frozen Phase 11 source changed: {name}")
    return lineages, {
        "result": "PASS", "phase_manifest_count": len(manifest_results),
        "phase_manifests": manifest_results, "phase11_sources_verified": sorted(contract["phase11_sources"]),
        "verification_completed_before_database_write": True,
    }


def _lineage_records(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[int, str], dict[str, Any]] = {}
    for row in raw:
        key = (int(row["phase"]), str(row["artifact_path"]))
        unique[key] = row
    records = []
    for row in sorted(unique.values(), key=lambda item: (item["phase"], item["artifact_path"])):
        content = f"{row['phase']}|{row['artifact_path']}|{row['artifact_sha256']}"
        records.append({
            "lineage_id": "LIN-" + hashlib.sha256(content.encode("utf-8")).hexdigest()[:24].upper(),
            **row, "authoritative": 1, "database_copy_role": "DERIVED_QUERY_REPRESENTATION",
        })
    return records


def _insert_exact(connection: sqlite3.Connection, table: str, record: dict[str, Any], primary_keys: list[str]) -> bool:
    where = " AND ".join(f"{key} = ?" for key in primary_keys)
    existing = connection.execute(
        f"SELECT * FROM {table} WHERE {where}", tuple(record[key] for key in primary_keys),
    ).fetchone()
    if existing is not None:
        actual = {key: existing[key] for key in existing.keys()}
        if actual != record:
            raise SourceConflictError(f"HARD_FAIL_SOURCE_CONFLICT: {table} {tuple(record[key] for key in primary_keys)}")
        return False
    columns = list(record)
    placeholders = ",".join("?" for _ in columns)
    try:
        connection.execute(
            f"INSERT INTO {table}({','.join(columns)}) VALUES({placeholders})",
            tuple(record[column] for column in columns),
        )
    except sqlite3.IntegrityError as error:
        raise SourceConflictError(f"HARD_FAIL_SOURCE_CONFLICT: {table}: {error}") from error
    return True


class HistoryIngestor:
    def __init__(self, project_root: Path, database_path: Path, contract_path: Path | None = None) -> None:
        self.project_root = project_root.resolve()
        self.database_path = database_path.resolve()
        self.contract_path = (contract_path or self.project_root / "contracts/monitoring_history_contract.json").resolve()

    def ingest(self, *, fail_after_records: int | None = None) -> IngestionResult:
        contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        raw_lineage, source_reconciliation = verify_frozen_sources(self.project_root, contract)
        records = self._construct_records(contract, _lineage_records(raw_lineage))
        connection = connect_history(self.database_path)
        try:
            initialize_history(connection, self.project_root / contract["schema"]["schema_path"])
            inserted = existing = processed = 0
            with connection:
                for table, rows, keys in records:
                    for row in rows:
                        changed = _insert_exact(connection, table, row, keys)
                        inserted += int(changed)
                        existing += int(not changed)
                        processed += 1
                        if fail_after_records is not None and processed >= fail_after_records:
                            raise RuntimeError("QUALIFICATION_FORCED_TRANSACTION_FAILURE")
            schema_qualification = qualify_schema(connection)
            if schema_qualification["result"] != "PASS" or schema_qualification["applicant_identifier_columns"]:
                raise RuntimeError("Monitoring-history schema qualification failed")
            table_counts = {table: table_count(connection, table) for table, _, _ in records}
            semantic = semantic_database_manifest(connection)
            status = "MATERIALIZED" if inserted else "IDEMPOTENT_NO_OP"
            return IngestionResult(status, inserted, existing, table_counts, semantic, source_reconciliation, schema_qualification)
        finally:
            connection.close()

    def _construct_records(self, contract: dict[str, Any], lineage: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]], list[str]]]:
        sources = contract["phase11_sources"]
        candidates = pd.read_parquet(self.project_root / sources["normalized_candidates"]["path"], engine="pyarrow")
        alerts = pd.read_parquet(self.project_root / sources["alerts"]["path"], engine="pyarrow")
        components = pd.read_parquet(self.project_root / sources["component_health"]["path"], engine="pyarrow")
        overall = pd.read_parquet(self.project_root / sources["overall_health"]["path"], engine="pyarrow")
        authorization = json.loads((self.project_root / sources["authorization"]["path"]).read_text(encoding="utf-8"))["results"]
        scopes = json.loads((self.project_root / sources["evidence_scope"]["path"]).read_text(encoding="utf-8"))["results"]
        expected = {
            "normalized_candidates": len(candidates), "alerts": len(alerts), "component_health": len(components),
            "overall_health": len(overall), "authorization": len(authorization), "evidence_scope": len(scopes),
        }
        for name, actual in expected.items():
            if actual != int(sources[name]["expected_rows"]):
                raise SourceVerificationError(f"Phase 11 source row count mismatch: {name}")
        if not alerts["alert_id"].is_unique or set(alerts["status"]) != {"OPEN"}:
            raise SourceVerificationError("Frozen Phase 11 alerts are not 329 unique initial OPEN alerts")

        phase11_manifest = next(item for item in contract["phase_manifests"] if item["phase"] == 11)
        phase11_payload = json.loads((self.project_root / phase11_manifest["path"]).read_text(encoding="utf-8"))
        auth_by_artifact = {row["artifact_id"]: row for row in authorization}
        scope_by_artifact = {row["artifact_id"]: row for row in scopes}
        overall_by_artifact = {row["artifact_id"]: row for row in overall.to_dict("records")}
        if set(auth_by_artifact) != set(overall_by_artifact) or set(scope_by_artifact) != set(overall_by_artifact):
            raise SourceVerificationError("Authorization, evidence scope and overall-health artifact grains differ")

        contract_sha = sha256_file(self.contract_path)
        schema_metadata = [{
            "schema_version": 1, "contract_id": contract["contract_id"], "contract_sha256": contract_sha,
            "created_from_phase11_manifest": phase11_manifest["sha256"],
            "database_role": contract["authority_model"]["database_role"], "authoritative_evidence": 0,
        }]
        phase_records = [{
            "phase": item["phase"], "control_id": item["control_id"], "manifest_path": item["path"],
            "manifest_sha256": item["sha256"], "approval_state": "APPROVED_FROZEN",
        } for item in contract["phase_manifests"]]

        run_records = []
        artifact_to_run = {}
        model = contract["model"]
        for artifact_id in sorted(overall_by_artifact):
            health = overall_by_artifact[artifact_id]
            auth = auth_by_artifact[artifact_id]
            scope = scope_by_artifact[artifact_id]
            if health["authorization_status"] != auth["authorization_status"] or health["evidence_scope"] != scope["evidence_scope"] or health["evidence_type"] != scope["evidence_type"]:
                raise SourceVerificationError(f"Phase 11 decision dimensions do not reconcile: {artifact_id}")
            history_run_id = _history_run_id(artifact_id)
            artifact_to_run[artifact_id] = history_run_id
            fingerprint_fields = [
                model["model_version"], health["scenario_id"], artifact_id, phase11_manifest["sha256"],
                auth["authorization_status"], scope["evidence_scope"],
            ]
            run_records.append({
                "history_run_id": history_run_id, "model_id": model["model_id"], "model_version": model["model_version"],
                "development_freeze_id": model["development_freeze_id"], "scenario_id": health["scenario_id"],
                "scenario_artifact_id": artifact_id, "authorization_state": auth["authorization_status"],
                "evidence_scope": scope["evidence_scope"], "overall_model_health": health["overall_model_health"],
                "evidence_type": scope["evidence_type"], "synthetic_evidence": int(scope["evidence_type"] == "SYNTHETIC_SCENARIO_EVIDENCE"),
                "calendar_interpretation": 0, "comparable_longitudinal_run": 0, "comparable_run_group_id": None,
                "period_start": None, "period_end": None, "source_phase11_manifest_sha256": phase11_manifest["sha256"],
                "run_fingerprint": _sha(fingerprint_fields), "source_created_utc": phase11_payload["created_utc"],
            })

        lineage_by_phase_hash: dict[tuple[int, str], list[str]] = {}
        for row in lineage:
            lineage_by_phase_hash.setdefault((row["phase"], row["artifact_sha256"]), []).append(row["artifact_path"])
        metric_records, metric_key_to_id = [], {}
        match_fields = ["run_id", "artifact_id", "component", "alert_class", "metric_id", "entity_type", "entity_id", "metric_severity", "evidence_type", "source_phase", "source_artifact_hash"]
        for source_row in candidates.to_dict("records"):
            canonical = {key: _value(value) for key, value in source_row.items()}
            source_row_key = _sha(canonical)
            metric_record_id = "MET-" + source_row_key[:24].upper()
            phase = int(canonical["source_phase"].replace("PHASE_", ""))
            paths = lineage_by_phase_hash.get((phase, canonical["source_artifact_hash"]), [])
            if not paths:
                raise SourceVerificationError(f"No authoritative lineage for metric source {phase}/{canonical['source_artifact_hash']}")
            metric_value = canonical["metric_value"]
            record = {
                "metric_record_id": metric_record_id, "history_run_id": artifact_to_run[canonical["artifact_id"]],
                "source_run_id": canonical["run_id"], "source_phase": canonical["source_phase"], "component": canonical["component"],
                "alert_class": canonical["alert_class"], "metric_id": canonical["metric_id"], "metric_role": canonical["control_role"],
                "entity_type": canonical["entity_type"], "entity_id": canonical["entity_id"],
                "metric_value_numeric": metric_value, "metric_value_text": None if metric_value is not None else "N/A",
                "metric_severity": canonical["metric_severity"], "evidence_status": canonical["evidence_status"],
                "authority_status": canonical["authority_status"], "materiality_class": canonical["materiality_class"],
                "evidence_type": canonical["evidence_type"], "reference_id": canonical["reference_id"],
                "source_artifact_path": sorted(paths)[0], "source_artifact_sha256": canonical["source_artifact_hash"],
                "source_row_key": source_row_key,
            }
            metric_records.append(record)
            key = tuple(canonical[field] for field in match_fields)
            if key in metric_key_to_id:
                raise SourceVerificationError("Normalized candidate logical key is not unique")
            metric_key_to_id[key] = metric_record_id

        alert_records, event_records = [], []
        for source_row in alerts.to_dict("records"):
            row = {key: _value(value) for key, value in source_row.items()}
            key = tuple(row[field] for field in match_fields)
            if key not in metric_key_to_id:
                raise SourceVerificationError(f"Alert does not reconcile to exactly one normalized candidate: {row['alert_id']}")
            alert_records.append({
                "alert_id": row["alert_id"], "history_run_id": artifact_to_run[row["artifact_id"]],
                "source_run_id": row["run_id"], "alert_key": row["alert_key"], "model_id": row["model_id"],
                "alert_class": row["alert_class"], "component": row["component"], "metric_id": row["metric_id"],
                "entity_type": row["entity_type"], "entity_id": row["entity_id"], "metric_value_numeric": row["metric_value"],
                "metric_severity": row["metric_severity"], "alert_severity": row["alert_severity"], "reason_code": row["reason_code"],
                "evidence_status": row["evidence_status"], "evidence_type": row["evidence_type"], "source_phase": row["source_phase"],
                "source_metric_record_id": metric_key_to_id[key], "source_artifact_sha256": row["source_artifact_hash"],
                "opened_source_utc": phase11_payload["created_utc"], "overall_health_contributor": row["overall_health_contributor"],
                "persistence_eligible": row["persistence_eligible"], "repeat_breach_status": row["repeat_breach_status"],
                "production_performance_claim": row["production_performance_claim"],
            })
            event_content = f"{row['alert_id']}|CREATED"
            event_records.append({
                "event_id": "EVT-" + hashlib.sha256(event_content.encode("utf-8")).hexdigest()[:24].upper(),
                "alert_id": row["alert_id"], "event_sequence": 1, "event_type": "CREATED", "from_status": None,
                "to_status": "OPEN", "event_utc": phase11_payload["created_utc"], "actor_type": "SYSTEM_IMPORT",
                "actor_label": "PHASE_11_FROZEN_IMPORT", "reason": "Imported frozen Phase 11 initial OPEN state",
                "source": "PHASE_11_IMPORT",
            })

        component_hash = sources["component_health"]["sha256"]
        component_records = [{
            "history_run_id": artifact_to_run[row["artifact_id"]], "component": row["component"],
            "health_state": row["component_health"], "alert_count": int(row["alert_count"]),
            "critical_alert_count": int(row["critical_alert_count"]), "warning_alert_count": int(row["warning_alert_count"]),
            "source_artifact_sha256": component_hash,
        } for row in components.to_dict("records")]
        run_health_records = [{
            "history_run_id": artifact_to_run[row["artifact_id"]], "authorization_state": row["authorization_status"],
            "evidence_scope": row["evidence_scope"], "overall_model_health": row["overall_model_health"],
            "synthetic_evidence_type": row["evidence_type"], "open_alert_count": int(row["open_alert_count"]),
            "critical_alert_count": int(row["critical_alert_count"]), "warning_alert_count": int(row["warning_alert_count"]),
            "source_authorization_sha256": sources["authorization"]["sha256"],
            "source_evidence_scope_sha256": sources["evidence_scope"]["sha256"],
            "source_overall_health_sha256": sources["overall_health"]["sha256"],
        } for row in overall.to_dict("records")]

        return [
            ("schema_metadata", schema_metadata, ["schema_version"]),
            ("phase_manifests", phase_records, ["phase"]),
            ("monitoring_runs", run_records, ["history_run_id"]),
            ("metric_evidence", metric_records, ["metric_record_id"]),
            ("alerts", alert_records, ["alert_id"]),
            ("alert_events", event_records, ["event_id"]),
            ("component_health", component_records, ["history_run_id", "component"]),
            ("run_health", run_health_records, ["history_run_id"]),
            ("artifact_lineage", lineage, ["lineage_id"]),
        ]
