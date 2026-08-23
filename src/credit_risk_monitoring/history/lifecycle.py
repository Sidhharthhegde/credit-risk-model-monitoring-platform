"""Append-only operational alert lifecycle service."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone


class AlertLifecycleService:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def current_status(self, alert_id: str) -> str:
        row = self.connection.execute(
            "SELECT current_status FROM v_current_alert_state WHERE alert_id = ?", (alert_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown alert: {alert_id}")
        return str(row[0])

    def _transition(self, alert_id: str, target: str, actor_label: str, reason: str, event_utc: str | None) -> str:
        if not actor_label.strip() or not reason.strip():
            raise ValueError("Actor label and reason are required; no enterprise identity is implied")
        current = self.current_status(alert_id)
        allowed = {"OPEN": "ACKNOWLEDGED", "ACKNOWLEDGED": "RESOLVED"}
        if allowed.get(current) != target:
            raise ValueError(f"Alert lifecycle transition is not permitted: {current} -> {target}")
        event_type = target
        sequence = int(self.connection.execute(
            "SELECT MAX(event_sequence) FROM alert_events WHERE alert_id = ?", (alert_id,),
        ).fetchone()[0]) + 1
        timestamp = event_utc or datetime.now(timezone.utc).isoformat()
        content = f"{alert_id}|{sequence}|{event_type}|{timestamp}|{actor_label}|{reason}"
        event_id = "EVT-" + hashlib.sha256(content.encode("utf-8")).hexdigest()[:24].upper()
        with self.connection:
            self.connection.execute(
                "INSERT INTO alert_events(event_id,alert_id,event_sequence,event_type,from_status,to_status,event_utc,actor_type,actor_label,reason,source) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (event_id, alert_id, sequence, event_type, current, target, timestamp, "LOCAL_DEMO_USER", actor_label, reason, "PHASE_12_OPERATIONAL_LEDGER"),
            )
        return event_id

    def acknowledge_alert(self, alert_id: str, actor_label: str, reason: str, *, event_utc: str | None = None) -> str:
        return self._transition(alert_id, "ACKNOWLEDGED", actor_label, reason, event_utc)

    def resolve_alert(self, alert_id: str, actor_label: str, reason: str, *, event_utc: str | None = None) -> str:
        return self._transition(alert_id, "RESOLVED", actor_label, reason, event_utc)
