"""Schema inspection and qualification helpers."""

from __future__ import annotations

import sqlite3
from typing import Any


EXPECTED_TABLES = {
    "schema_metadata", "phase_manifests", "monitoring_runs", "metric_evidence", "alerts",
    "alert_events", "component_health", "run_health", "artifact_lineage",
}
EXPECTED_VIEWS = {
    "v_current_alert_state", "v_open_alerts", "v_open_critical_alerts", "v_current_run_alert_counts", "v_run_summary",
    "v_run_component_health", "v_alerts_with_lineage", "v_metric_evidence_with_lineage",
    "v_blocked_runs", "v_synthetic_evidence", "v_comparable_metric_history",
}


def qualify_schema(connection: sqlite3.Connection) -> dict[str, Any]:
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'") if not row[0].startswith("sqlite_")}
    views = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='view'")}
    foreign_keys = int(connection.execute("PRAGMA foreign_keys").fetchone()[0]) == 1
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    return {
        "result": "PASS" if tables == EXPECTED_TABLES and views == EXPECTED_VIEWS and foreign_keys and version == 1 else "FAIL",
        "schema_version": version,
        "foreign_keys_enabled": foreign_keys,
        "tables": sorted(tables),
        "views": sorted(views),
        "expected_tables_present": tables == EXPECTED_TABLES,
        "expected_views_present": views == EXPECTED_VIEWS,
        "applicant_identifier_columns": [
            row[1] for table in tables for row in connection.execute(f"PRAGMA table_info({table})")
            if row[1].upper() in {"SK_ID_CURR", "APPLICANT_ID", "CUSTOMER_ID"}
        ],
    }
