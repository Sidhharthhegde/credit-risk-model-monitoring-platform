"""Parameterized repository API for later dashboard and investigation consumers."""

from __future__ import annotations

import sqlite3
from typing import Any


def _dicts(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


class HistoryRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def list_runs(self) -> list[dict[str, Any]]:
        return _dicts(self.connection.execute("SELECT * FROM v_run_summary ORDER BY history_run_id"))

    def get_run(self, history_run_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM v_run_summary WHERE history_run_id = ?", (history_run_id,)).fetchone()
        return dict(row) if row else None

    def list_alerts(self, *, severity: str | None = None, status: str | None = None, component: str | None = None, scenario_id: str | None = None) -> list[dict[str, Any]]:
        clauses, values = [], []
        for column, value in [("a.alert_severity", severity), ("s.current_status", status), ("a.component", component), ("r.scenario_id", scenario_id)]:
            if value is not None:
                clauses.append(f"{column} = ?")
                values.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        sql = "SELECT a.*, s.current_status, s.latest_event_utc FROM alerts a JOIN v_current_alert_state s USING(alert_id) JOIN monitoring_runs r USING(history_run_id)" + where + " ORDER BY a.alert_id"
        return _dicts(self.connection.execute(sql, values))

    def get_alert(self, alert_id: str) -> dict[str, Any] | None:
        rows = self.connection.execute("SELECT * FROM v_alerts_with_lineage WHERE alert_id = ?", (alert_id,)).fetchall()
        return dict(rows[0]) if rows else None

    def get_alert_history(self, alert_id: str) -> list[dict[str, Any]]:
        return _dicts(self.connection.execute("SELECT * FROM alert_events WHERE alert_id = ? ORDER BY event_sequence", (alert_id,)))

    def get_open_critical_alerts(self) -> list[dict[str, Any]]:
        return _dicts(self.connection.execute("SELECT * FROM v_open_critical_alerts ORDER BY alert_id"))

    def get_component_health(self, history_run_id: str) -> list[dict[str, Any]]:
        return _dicts(self.connection.execute("SELECT * FROM component_health WHERE history_run_id = ? ORDER BY component", (history_run_id,)))

    def get_overall_health(self, history_run_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM run_health WHERE history_run_id = ?", (history_run_id,)).fetchone()
        return dict(row) if row else None

    def list_blocked_runs(self) -> list[dict[str, Any]]:
        return _dicts(self.connection.execute("SELECT * FROM v_blocked_runs ORDER BY history_run_id"))

    def get_metric_evidence(self, *, metric_id: str | None = None, entity_id: str | None = None, scenario_id: str | None = None) -> list[dict[str, Any]]:
        clauses, values = [], []
        for column, value in [("m.metric_id", metric_id), ("m.entity_id", entity_id), ("r.scenario_id", scenario_id)]:
            if value is not None:
                clauses.append(f"{column} = ?")
                values.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        sql = "SELECT m.* FROM metric_evidence m JOIN monitoring_runs r USING(history_run_id)" + where + " ORDER BY m.metric_record_id"
        return _dicts(self.connection.execute(sql, values))

    def get_evidence_lineage(self, record_id: str) -> list[dict[str, Any]]:
        metric = self.connection.execute("SELECT source_phase,source_artifact_sha256 FROM metric_evidence WHERE metric_record_id = ?", (record_id,)).fetchone()
        if metric:
            phase = int(str(metric["source_phase"]).replace("PHASE_", ""))
            return _dicts(self.connection.execute("SELECT * FROM artifact_lineage WHERE phase = ? AND artifact_sha256 = ?", (phase, metric["source_artifact_sha256"])))
        alert = self.connection.execute("SELECT source_phase,source_artifact_sha256 FROM alerts WHERE alert_id = ?", (record_id,)).fetchone()
        if alert:
            phase = int(str(alert["source_phase"]).replace("PHASE_", ""))
            return _dicts(self.connection.execute("SELECT * FROM artifact_lineage WHERE phase = ? AND artifact_sha256 = ?", (phase, alert["source_artifact_sha256"])))
        return []

    def get_synthetic_performance_runs(self) -> list[dict[str, Any]]:
        return _dicts(self.connection.execute("SELECT * FROM v_synthetic_evidence ORDER BY history_run_id"))

    def get_comparable_metric_history(self, metric_id: str, entity_id: str | None = None) -> list[dict[str, Any]]:
        if entity_id is None:
            return _dicts(self.connection.execute("SELECT * FROM v_comparable_metric_history WHERE metric_id = ? ORDER BY period_start", (metric_id,)))
        return _dicts(self.connection.execute("SELECT * FROM v_comparable_metric_history WHERE metric_id = ? AND entity_id = ? ORDER BY period_start", (metric_id, entity_id)))
