"""Logical database digests independent of SQLite page layout."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any


TABLE_KEYS = {
    "schema_metadata": ["schema_version"],
    "phase_manifests": ["phase"],
    "monitoring_runs": ["history_run_id"],
    "metric_evidence": ["metric_record_id"],
    "alerts": ["alert_id"],
    "alert_events": ["alert_id", "event_sequence"],
    "component_health": ["history_run_id", "component"],
    "run_health": ["history_run_id"],
    "artifact_lineage": ["lineage_id"],
}
IMMUTABLE_TABLES = [
    "schema_metadata", "phase_manifests", "monitoring_runs", "metric_evidence", "alerts",
    "component_health", "run_health", "artifact_lineage",
]


def _canonical(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, float):
        return float(format(value, ".17g"))
    return value


def table_semantic_sha256(connection: sqlite3.Connection, table: str) -> tuple[str, int]:
    if table not in TABLE_KEYS:
        raise ValueError(f"Unknown governed digest table: {table}")
    order = ", ".join(TABLE_KEYS[table])
    rows = []
    for row in connection.execute(f"SELECT * FROM {table} ORDER BY {order}"):
        rows.append({key: _canonical(row[key]) for key in row.keys()})
    serialized = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest(), len(rows)


def semantic_database_manifest(connection: sqlite3.Connection) -> dict[str, Any]:
    tables: dict[str, Any] = {}
    for table in TABLE_KEYS:
        digest, rows = table_semantic_sha256(connection, table)
        tables[table] = {"semantic_sha256": digest, "row_count": rows}
    immutable_serialized = json.dumps(
        {table: tables[table]["semantic_sha256"] for table in IMMUTABLE_TABLES},
        sort_keys=True, separators=(",", ":"),
    )
    complete_serialized = json.dumps(
        {table: value["semantic_sha256"] for table, value in tables.items()},
        sort_keys=True, separators=(",", ":"),
    )
    return {
        "digest_method": "CANONICAL_JSON_SORTED_BY_PRIMARY_KEY_SHA256",
        "tables": tables,
        "immutable_evidence_semantic_sha256": hashlib.sha256(immutable_serialized.encode("utf-8")).hexdigest(),
        "database_semantic_sha256": hashlib.sha256(complete_serialized.encode("utf-8")).hexdigest(),
        "physical_database_hash_is_authoritative": False,
    }
