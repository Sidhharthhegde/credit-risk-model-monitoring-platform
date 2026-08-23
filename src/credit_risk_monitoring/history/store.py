"""SQLite connection and versioned schema installation."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect_history(path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    path = path.resolve()
    if read_only:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        connection.close()
        raise RuntimeError("SQLite foreign-key enforcement could not be enabled")
    return connection


def initialize_history(connection: sqlite3.Connection, schema_path: Path) -> None:
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version == 0:
        connection.executescript(schema_path.read_text(encoding="utf-8"))
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version != 1:
        raise RuntimeError(f"Unsupported monitoring-history schema version: {version}")


def table_count(connection: sqlite3.Connection, table: str) -> int:
    allowed = {
        "schema_metadata", "phase_manifests", "monitoring_runs", "metric_evidence", "alerts",
        "alert_events", "component_health", "run_health", "artifact_lineage",
    }
    if table not in allowed:
        raise ValueError(f"Unknown governed table: {table}")
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
