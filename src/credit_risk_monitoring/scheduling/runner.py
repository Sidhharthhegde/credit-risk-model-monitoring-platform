"""Thin scheduler-safe wrapper around the frozen Phase 14 orchestrator."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from credit_risk_monitoring.history.digest import semantic_database_manifest
from credit_risk_monitoring.history.store import connect_history
from credit_risk_monitoring.orchestration.runner import MonitoringOrchestrator
from credit_risk_monitoring.orchestration.gates import FrozenEvidenceWriteError
from credit_risk_monitoring.qualification.binding import sha256_file

from .exit_codes import ExitCode
from .locking import ActiveLockError, ExecutionLock, InvalidLockError
from .receipts import AggregateEventLog, utc_now, write_json_atomic


@dataclass(frozen=True)
class ScheduledRunResult:
    exit_code: ExitCode
    receipt_path: Path
    execution_id: str


class BindingFailure(RuntimeError):
    exit_code = ExitCode.FROZEN_SOURCE_VERIFICATION_FAILURE


class ManifestChainFailure(BindingFailure):
    exit_code = ExitCode.MANIFEST_CHAIN_FAILURE


class DatabaseBindingFailure(BindingFailure):
    exit_code = ExitCode.IMMUTABLE_EVIDENCE_DIGEST_FAILURE


class ReportBindingFailure(BindingFailure):
    exit_code = ExitCode.REPORT_OR_QUERY_FAILURE


class ScheduledExecutionRunner:
    def __init__(self, project_root: Path, *, runtime_root: Path | None = None) -> None:
        self.root = project_root.resolve()
        contract_path = self.root / "contracts/final_project_release_contract.json"
        self.contract = json.loads(contract_path.read_text(encoding="utf-8"))
        configured = self.root / self.contract["execution"]["runtime_root"]
        self.runtime_root = (runtime_root or configured).resolve()

    def run(self, *, profile: str = "VERIFY_FROZEN", recover_stale_lock: bool = False) -> ScheduledRunResult:
        now = datetime.now(timezone.utc)
        execution_id = f"SCHED-{now.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid.uuid4().hex[:8]}"
        run_dir = self.runtime_root / "runs" / execution_id
        receipt_path = run_dir / "execution_receipt.json"
        log = AggregateEventLog(run_dir / "execution_events.jsonl", execution_id)
        started = utc_now()
        receipt = self._base_receipt(execution_id, profile, started)
        lock = ExecutionLock(
            self.runtime_root / "execution.lock.json",
            execution_id,
            int(self.contract["locking"]["maximum_age_seconds"]),
        )
        acquired = False
        code = ExitCode.UNEXPECTED_FAILURE
        try:
            if profile not in {"VERIFY_FROZEN", "ISOLATED_QUALIFICATION_REPLAY"}:
                raise ValueError(f"Unsupported execution profile: {profile}")
            lock_payload = lock.acquire(recover_stale=recover_stale_lock, recovery_dir=run_dir)
            acquired = True
            receipt["lock"].update({"status": "ACQUIRED", "payload": lock_payload, "recovery_evidence": lock.recovered_lock_path})
            log.write("LOCK", "INFO", "Exclusive execution lock acquired")
            self._verify_phase14_binding()
            before = self._database_snapshot()
            receipt["bindings"]["database_before"] = before
            self._verify_report_binding()
            orchestrator = MonitoringOrchestrator(self.root)
            if profile == "VERIFY_FROZEN":
                result = orchestrator.verify_frozen(generate_report=False)
                receipt["orchestration"] = {"mode": result.mode, "status": result.status, "stage_count": len(result.stages)}
            else:
                replay_root = self.root / "artifacts/qualification_replay/scheduled" / execution_id
                result, replay = orchestrator.qualification_replay(replay_root)
                receipt["orchestration"] = {"mode": result.mode, "status": result.status, "stage_count": len(result.stages), "replay": replay}
            after = self._database_snapshot()
            receipt["bindings"]["database_after"] = after
            if before != after:
                raise DatabaseBindingFailure("Scheduled execution changed monitoring-history state")
            receipt["immutability"] = {
                "phase_0_through_14_unchanged": True,
                "database_unchanged": True,
                "alert_lifecycle_mutated": False,
                "report_generated": False,
                "report_verified": True,
            }
            receipt.update({
                "manifest_chain_verification": "PASS",
                "immutable_evidence_verification": "PASS",
                "frozen_write_attempted": False,
                "frozen_write_blocked": False,
                "database_mutated": False,
                "alert_lifecycle_mutated": False,
                "report_generated": False,
                "report_output_path": "reports/monitoring_report/MONITORING-REPORT-01",
            })
            receipt["status"] = "PASS"
            code = ExitCode.SUCCESS
            log.write("COMPLETE", "INFO", "Scheduled verification completed")
        except ActiveLockError as exc:
            code = ExitCode.ACTIVE_LOCK
            receipt["status"] = "BLOCKED"
            receipt["lock"].update({"status": "ACTIVE_LOCK_REJECTED"})
            receipt["error"] = self._safe_error(exc)
            log.write("LOCK", "WARNING", "Execution rejected because an active lock exists")
        except InvalidLockError as exc:
            code = ExitCode.INVALID_OR_STALE_LOCK
            receipt["status"] = "BLOCKED"
            receipt["lock"].update({"status": "INVALID_OR_STALE_LOCK_REJECTED"})
            receipt["error"] = self._safe_error(exc)
            log.write("LOCK", "ERROR", "Execution rejected because the lock is invalid or stale")
        except BindingFailure as exc:
            code = exc.exit_code
            receipt["status"] = "FAIL"
            receipt["error"] = self._safe_error(exc)
            log.write("BINDING", "ERROR", "Frozen binding verification failed")
        except ValueError as exc:
            code = ExitCode.CONFIGURATION_OR_CONTRACT_FAILURE
            receipt["status"] = "FAIL"
            receipt["error"] = self._safe_error(exc)
            log.write("CONFIGURATION", "ERROR", "Configuration validation failed")
        except FrozenEvidenceWriteError as exc:
            code = ExitCode.FROZEN_WRITE_ATTEMPT
            receipt["status"] = "FAIL"
            receipt["frozen_write_attempted"] = True
            receipt["frozen_write_blocked"] = True
            receipt["error"] = self._safe_error(exc)
            log.write("FROZEN_WRITE_GUARD", "ERROR", "A frozen-evidence write attempt was blocked")
        except RuntimeError as exc:
            if "Part A binding" in str(exc):
                code = ExitCode.FROZEN_SOURCE_VERIFICATION_FAILURE
            elif "Frozen phase manifest changed" in str(exc):
                code = ExitCode.MANIFEST_CHAIN_FAILURE
            else:
                code = ExitCode.ORCHESTRATION_FAILURE
            receipt["status"] = "FAIL"
            receipt["error"] = self._safe_error(exc)
            log.write("ORCHESTRATION", "ERROR", "Frozen orchestration failed")
        except (ImportError, ModuleNotFoundError) as exc:
            code = ExitCode.DEPENDENCY_OR_ENVIRONMENT_FAILURE
            receipt["status"] = "FAIL"
            receipt["error"] = self._safe_error(exc)
            log.write("ENVIRONMENT", "ERROR", "A required runtime dependency is unavailable")
        except Exception as exc:  # pragma: no cover - defensive outer boundary
            code = ExitCode.UNEXPECTED_FAILURE
            receipt["status"] = "FAIL"
            receipt["error"] = self._safe_error(exc)
            log.write("UNEXPECTED", "ERROR", "Unexpected scheduled-execution failure")
        finally:
            if acquired:
                lock.release()
                receipt["lock"]["released"] = True
            if log.failure is not None:
                code = ExitCode.RECEIPT_OR_LOGGING_FAILURE
                receipt["status"] = "FAIL"
                receipt["error"] = dict(log.failure)
            self._synchronize_terminal_fields(receipt, code)
            try:
                write_json_atomic(receipt_path, receipt)
            except Exception as exc:
                code = ExitCode.RECEIPT_OR_LOGGING_FAILURE
                receipt["status"] = "FAIL"
                receipt["error"] = self._safe_error(exc)
                self._synchronize_terminal_fields(receipt, code)
                receipt_path = run_dir / "receipt_failure.json"
                receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return ScheduledRunResult(code, receipt_path, execution_id)

    def _base_receipt(self, execution_id: str, profile: str, started: str) -> dict:
        return {
            "schema_version": "1.0.0",
            "execution_id": execution_id,
            "profile": profile,
            "execution_mode": "UNATTENDED_SCHEDULED_WRAPPER",
            "command_profile": profile,
            "orchestrator_id": "MONITORING-ORCHESTRATOR-01",
            "started_utc": started,
            "finished_utc": None,
            "completed_utc": None,
            "status": "FAIL",
            "execution_status": "FAIL",
            "exit_code": int(ExitCode.UNEXPECTED_FAILURE),
            "lock": {"status": "NOT_ACQUIRED", "released": False},
            "bindings": {
                "phase14_manifest_sha256": self.contract["frozen_phase14_binding"]["manifest_sha256"],
                "phase14_commit": self.contract["frozen_phase14_binding"]["commit"],
            },
            "immutability": {
                "phase_0_through_14_unchanged": False,
                "database_unchanged": False,
                "alert_lifecycle_mutated": False,
                "report_generated": False,
                "report_verified": False,
            },
            "error": None,
            "error_class": None,
            "error_message": None,
            "phase14_manifest_sha256": self.contract["frozen_phase14_binding"]["manifest_sha256"],
            "manifest_chain_verification": "NOT_RUN",
            "immutable_evidence_verification": "NOT_RUN",
            "frozen_write_attempted": False,
            "frozen_write_blocked": False,
            "database_mutated": False,
            "alert_lifecycle_mutated": False,
            "report_generated": False,
            "report_output_path": None,
        }

    def _verify_phase14_binding(self) -> None:
        binding = self.contract["frozen_phase14_binding"]
        path = self.root / binding["manifest_path"]
        if sha256_file(path) != binding["manifest_sha256"]:
            raise ManifestChainFailure("Frozen Phase 14 manifest does not match the release contract")

    def _verify_report_binding(self) -> None:
        manifest_path = self.root / "reports/monitoring_report/MONITORING-REPORT-01/report_manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for artifact in manifest["files"]:
                path = manifest_path.parent / artifact["path"]
                if sha256_file(path) != artifact["sha256"]:
                    raise ReportBindingFailure("A frozen Phase 14 report artifact changed")
        except ReportBindingFailure:
            raise
        except Exception as exc:
            raise ReportBindingFailure("Frozen report manifest is invalid") from exc

    def _database_snapshot(self) -> dict:
        phase14 = json.loads((self.root / "contracts/final_lifecycle_qualification_contract.json").read_text(encoding="utf-8"))
        path = self.root / phase14["database_binding"]["path"]
        try:
            with connect_history(path, read_only=True) as connection:
                semantic = semantic_database_manifest(connection)
                alert_events = connection.execute("SELECT COUNT(*) FROM alert_events").fetchone()[0]
                alerts = connection.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
            return {
                "complete_semantic_sha256": semantic["database_semantic_sha256"],
                "immutable_evidence_semantic_sha256": semantic["immutable_evidence_semantic_sha256"],
                "alert_count": alerts,
                "alert_event_count": alert_events,
            }
        except Exception as exc:
            raise DatabaseBindingFailure("Monitoring-history database binding failed") from exc

    @staticmethod
    def _safe_error(exc: Exception) -> dict:
        return {"type": type(exc).__name__, "message": str(exc)[:500]}

    @staticmethod
    def _synchronize_terminal_fields(receipt: dict, code: ExitCode) -> None:
        completed = utc_now()
        receipt["exit_code"] = int(code)
        receipt["finished_utc"] = completed
        receipt["completed_utc"] = completed
        receipt["execution_status"] = receipt["status"]
        if receipt["error"] is None:
            receipt["error_class"] = None
            receipt["error_message"] = None
        else:
            receipt["error_class"] = receipt["error"]["type"]
            receipt["error_message"] = receipt["error"]["message"]
