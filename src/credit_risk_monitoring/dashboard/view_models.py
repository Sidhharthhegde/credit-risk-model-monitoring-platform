"""Immutable view models containing governed values without analytics logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScenarioView:
    history_run_id: str
    scenario_id: str
    artifact_id: str
    label: str
    authorization: str
    evidence_scope: str
    evidence_type: str
    overall_health: str
    current_open: int
    current_warning: int
    current_critical: int
    current_acknowledged: int
    current_resolved: int
    phase11_source_open: int
    synthetic: bool


@dataclass(frozen=True)
class MetricView:
    metric_record_id: str
    scenario_id: str
    artifact_id: str
    component: str
    metric_id: str
    entity_type: str
    entity_id: str
    value: float | None
    metric_severity: str
    metric_role: str
    materiality_class: str
    evidence_status: str
    evidence_type: str | None
    source_phase: str
    source_artifact_sha256: str


@dataclass(frozen=True)
class AlertView:
    alert_id: str
    scenario_id: str
    artifact_id: str
    component: str
    metric_id: str
    entity_type: str
    entity_id: str
    metric_value: float | None
    metric_severity: str
    alert_severity: str
    current_status: str
    reason_code: str
    evidence_status: str
    evidence_type: str
    source_phase: str
    source_artifact_sha256: str
    metric_role: str
    materiality_class: str
    lineage: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class DashboardSnapshot:
    scenarios: tuple[ScenarioView, ...]
    metric_count: int
    alert_count: int
    open_alert_count: int
    open_critical_count: int
    blocked_run_count: int
    synthetic_run_count: int
    comparable_history_count: int
