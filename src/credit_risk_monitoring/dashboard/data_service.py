"""Thin Phase 12 repository adapter producing immutable dashboard view models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from credit_risk_monitoring.history.digest import semantic_database_manifest
from credit_risk_monitoring.history.lifecycle import AlertLifecycleService
from credit_risk_monitoring.history.queries import HistoryRepository
from credit_risk_monitoring.history.store import connect_history
from credit_risk_monitoring.qualification.binding import sha256_file

from .view_models import AlertView, DashboardSnapshot, MetricView, ScenarioView


class DashboardBindingError(RuntimeError):
    pass


class DashboardDataService:
    def __init__(self, project_root: Path, database_path: Path, *, writable: bool = False) -> None:
        self.project_root = project_root.resolve()
        self.database_path = database_path.resolve()
        self.contract_path = self.project_root / "contracts/monitoring_dashboard_contract.json"
        self.contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        policy_path = self.project_root / self.contract["display_policy"]["path"]
        self.policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        self._verify_bindings(policy_path)
        self.connection = connect_history(self.database_path, read_only=not writable)
        semantic = semantic_database_manifest(self.connection)
        if semantic["immutable_evidence_semantic_sha256"] != self.contract["frozen_phase12_binding"]["immutable_evidence_semantic_sha256"]:
            self.connection.close()
            raise DashboardBindingError("Phase 12 immutable-evidence semantic digest does not match the frozen dashboard contract")
        self.repository = HistoryRepository(self.connection)
        self.lifecycle = AlertLifecycleService(self.connection) if writable else None

    def _verify_bindings(self, policy_path: Path) -> None:
        binding = self.contract["frozen_phase12_binding"]
        checks = [
            (self.project_root / binding["manifest_path"], binding["manifest_sha256"]),
            (self.project_root / binding["repository_path"], binding["repository_sha256"]),
            (self.project_root / binding["lifecycle_service_path"], binding["lifecycle_service_sha256"]),
            (policy_path, self.contract["display_policy"]["sha256"]),
        ]
        for path, expected in checks:
            if sha256_file(path) != expected:
                raise DashboardBindingError(f"Frozen dashboard dependency changed: {path}")

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "DashboardDataService":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def scenarios(self) -> tuple[ScenarioView, ...]:
        labels = self.policy["scenario_labels"]
        return tuple(ScenarioView(
            history_run_id=row["history_run_id"], scenario_id=row["scenario_id"],
            artifact_id=row["scenario_artifact_id"], label=labels[row["scenario_artifact_id"]],
            authorization=row["authorization_state"], evidence_scope=row["evidence_scope"],
            evidence_type=row["evidence_type"], overall_health=row["overall_model_health"],
            current_open=row["current_open_alert_count"], current_warning=row["current_open_warning_count"],
            current_critical=row["current_open_critical_count"], current_acknowledged=row["current_acknowledged_alert_count"],
            current_resolved=row["current_resolved_alert_count"], phase11_source_open=row["phase11_source_open_alert_count"],
            synthetic=bool(row["synthetic_evidence"]),
        ) for row in self.repository.list_runs())

    def snapshot(self) -> DashboardSnapshot:
        scenarios = self.scenarios()
        metrics = self.repository.get_metric_evidence()
        alerts = self.repository.list_alerts()
        return DashboardSnapshot(
            scenarios=scenarios, metric_count=len(metrics), alert_count=len(alerts),
            open_alert_count=sum(row.current_open for row in scenarios),
            open_critical_count=sum(row.current_critical for row in scenarios),
            blocked_run_count=sum(row.authorization != "AUTHORIZED" for row in scenarios),
            synthetic_run_count=sum(row.synthetic for row in scenarios),
            comparable_history_count=len(self.repository.get_comparable_metric_history("feature_psi")),
        )

    def component_health(self, history_run_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(self.repository.get_component_health(history_run_id))

    def metrics(self, *, component: str | None = None, scenario_id: str | None = None, metric_id: str | None = None) -> tuple[MetricView, ...]:
        rows = self.repository.get_metric_evidence(metric_id=metric_id, scenario_id=scenario_id)
        views = []
        artifact_by_run = {scenario.history_run_id: scenario.artifact_id for scenario in self.scenarios()}
        for row in rows:
            if component is not None and row["component"] != component:
                continue
            views.append(MetricView(
                metric_record_id=row["metric_record_id"], scenario_id=next(s.scenario_id for s in self.scenarios() if s.history_run_id == row["history_run_id"]),
                artifact_id=artifact_by_run[row["history_run_id"]], component=row["component"], metric_id=row["metric_id"],
                entity_type=row["entity_type"], entity_id=row["entity_id"], value=row["metric_value_numeric"],
                metric_severity=row["metric_severity"], metric_role=row["metric_role"], materiality_class=row["materiality_class"],
                evidence_status=row["evidence_status"], evidence_type=row["evidence_type"], source_phase=row["source_phase"],
                source_artifact_sha256=row["source_artifact_sha256"],
            ))
        return tuple(views)

    def alerts(self, **filters: str | None) -> tuple[AlertView, ...]:
        allowed = {key: filters.get(key) for key in ["severity", "status", "component", "scenario_id"]}
        rows = self.repository.list_alerts(**allowed)
        metrics = {row.metric_record_id: row for row in self.metrics()}
        views = []
        for row in rows:
            metric = metrics[row["source_metric_record_id"]]
            lineage = tuple(self.repository.get_evidence_lineage(row["alert_id"]))
            views.append(AlertView(
                alert_id=row["alert_id"], scenario_id=metric.scenario_id, artifact_id=metric.artifact_id,
                component=row["component"], metric_id=row["metric_id"], entity_type=row["entity_type"], entity_id=row["entity_id"],
                metric_value=row["metric_value_numeric"], metric_severity=row["metric_severity"], alert_severity=row["alert_severity"],
                current_status=row["current_status"], reason_code=row["reason_code"], evidence_status=row["evidence_status"],
                evidence_type=row["evidence_type"], source_phase=row["source_phase"], source_artifact_sha256=row["source_artifact_sha256"],
                metric_role=metric.metric_role, materiality_class=metric.materiality_class, lineage=lineage,
            ))
        return tuple(views)

    def acknowledge(self, alert_id: str, actor_label: str, reason: str, *, confirmed: bool) -> str:
        if not confirmed:
            raise ValueError("Explicit lifecycle confirmation is required")
        if self.lifecycle is None:
            raise RuntimeError("Dashboard service was opened read-only")
        return self.lifecycle.acknowledge_alert(alert_id, actor_label, reason)

    def resolve(self, alert_id: str, actor_label: str, reason: str, *, confirmed: bool) -> str:
        if not confirmed:
            raise ValueError("Explicit lifecycle confirmation is required")
        if self.lifecycle is None:
            raise RuntimeError("Dashboard service was opened read-only")
        return self.lifecycle.resolve_alert(alert_id, actor_label, reason)

    def segment_registry(self) -> dict[str, Any]:
        return dict(self.policy["segment_registry"])

    def comparable_history_available(self) -> bool:
        return bool(self.repository.get_comparable_metric_history("feature_psi"))
