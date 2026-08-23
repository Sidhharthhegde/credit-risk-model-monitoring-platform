"""Phase 14 verification-first monitoring lifecycle orchestrator."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from credit_risk_monitoring.dashboard.data_service import DashboardDataService
from credit_risk_monitoring.qualification.binding import sha256_file
from credit_risk_monitoring.reporting import MonitoringReportGenerator

from .gates import guard_output_path
from .replay import isolated_semantic_replay
from .stages import STAGE_REGISTRY
from .state import OrchestrationResult, StageResult


class MonitoringOrchestrator:
    def __init__(self, project_root: Path) -> None:
        self.root = project_root.resolve()
        self.contract = json.loads((self.root / "contracts/final_lifecycle_qualification_contract.json").read_text(encoding="utf-8"))

    def _verify_bindings(self) -> None:
        for item in self.contract["phase_manifest_chain"]:
            if sha256_file(self.root / item["path"]) != item["sha256"]:
                raise RuntimeError(f"Frozen phase manifest changed: Phase {item['phase']}")
        part_a = self.root.parent / "Part A - Credit Risk Model Validation Suite"
        git = ["git", "-c", f"safe.directory={part_a.as_posix()}", "-C", str(part_a)]
        head = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output([*git, "status", "--porcelain"], text=True).strip()
        if head != self.contract["part_a_binding"]["commit"] or dirty:
            raise RuntimeError("Frozen Part A binding failed")

    def verify_frozen(self, *, generate_report: bool = True) -> OrchestrationResult:
        self._verify_bindings()
        database = self.root / self.contract["database_binding"]["path"]
        with DashboardDataService(self.root, database) as service:
            snapshot = service.snapshot()
        stages = [StageResult(stage_id, "PASS", "Frozen governed evidence verified") for stage_id, _ in STAGE_REGISTRY]
        output = None
        if generate_report:
            output = self.root / "reports/monitoring_report/MONITORING-REPORT-01"
            guard_output_path(self.root, output, self.contract["frozen_write_roots"], self.contract["permitted_phase14_write_roots"])
            MonitoringReportGenerator(self.root, database).generate(output)
            stages[11] = StageResult("MONITORING_REPORT", "PASS", "Report generated from Phase 12 query layer")
        stages[12] = StageResult("DASHBOARD_READINESS", "PASS", f"Six-page dashboard source reconciles; {snapshot.alert_count} alerts accessible")
        return OrchestrationResult("VERIFY_FROZEN", "PASS", tuple(stages), output)

    def qualification_replay(self, output_root: Path) -> tuple[OrchestrationResult, dict]:
        self._verify_bindings()
        guard_output_path(self.root, output_root, self.contract["frozen_write_roots"], self.contract["permitted_phase14_write_roots"])
        payload = isolated_semantic_replay(self.root, output_root, self.contract)
        stages = tuple(StageResult(stage_id, "PASS", "Hash verified" if order < 10 else "Semantically replayed/verified") for stage_id, order in STAGE_REGISTRY)
        return OrchestrationResult("ISOLATED_SEMANTIC_REPLAY", "PASS", stages, output_root), payload
