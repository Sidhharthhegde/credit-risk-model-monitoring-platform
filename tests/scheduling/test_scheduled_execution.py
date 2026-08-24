from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from credit_risk_monitoring.scheduling.exit_codes import ExitCode
from credit_risk_monitoring.scheduling.locking import ActiveLockError, ExecutionLock, InvalidLockError
import credit_risk_monitoring.scheduling.runner as runner_module
from credit_risk_monitoring.orchestration.gates import FrozenEvidenceWriteError
from credit_risk_monitoring.scheduling.runner import (
    ManifestChainFailure,
    ReportBindingFailure,
    ScheduledExecutionRunner,
)


ROOT = Path(__file__).resolve().parents[2]


def _write_lock(path: Path, created: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": "1.0.0", "execution_id": "prior", "pid": 1,
        "host": "fixture", "created_utc": created.isoformat(),
    }), encoding="utf-8")


def test_lock_acquire_and_owner_release(tmp_path: Path) -> None:
    path = tmp_path / "execution.lock.json"
    lock = ExecutionLock(path, "current", 60)
    lock.acquire()
    assert path.exists()
    lock.release()
    assert not path.exists()


def test_active_lock_rejected(tmp_path: Path) -> None:
    path = tmp_path / "execution.lock.json"
    _write_lock(path, datetime.now(timezone.utc))
    try:
        ExecutionLock(path, "current", 60).acquire()
    except ActiveLockError:
        pass
    else:
        raise AssertionError("active lock was accepted")


def test_stale_lock_requires_explicit_recovery(tmp_path: Path) -> None:
    path = tmp_path / "execution.lock.json"
    _write_lock(path, datetime.now(timezone.utc) - timedelta(hours=2))
    try:
        ExecutionLock(path, "current", 60).acquire()
    except InvalidLockError:
        pass
    else:
        raise AssertionError("stale lock was silently recovered")


def test_stale_lock_recovery_writes_evidence(tmp_path: Path) -> None:
    path = tmp_path / "execution.lock.json"
    evidence = tmp_path / "run"
    _write_lock(path, datetime.now(timezone.utc) - timedelta(hours=2))
    lock = ExecutionLock(path, "current", 60)
    lock.acquire(recover_stale=True, recovery_dir=evidence)
    recovered = json.loads((evidence / "recovered_stale_lock.json").read_text(encoding="utf-8"))
    assert recovered["stale_lock"]["execution_id"] == "prior"
    assert recovered["recovered_by_execution_id"] == "current"
    lock.release()


def test_corrupt_lock_fails_closed_even_with_recovery_flag(tmp_path: Path) -> None:
    path = tmp_path / "execution.lock.json"
    path.write_text("not-json", encoding="utf-8")
    try:
        ExecutionLock(path, "current", 60).acquire(recover_stale=True, recovery_dir=tmp_path / "run")
    except InvalidLockError:
        pass
    else:
        raise AssertionError("corrupt lock was recovered")


def test_default_scheduled_verification_is_read_only(tmp_path: Path) -> None:
    result = ScheduledExecutionRunner(ROOT, runtime_root=tmp_path).run()
    receipt = json.loads(result.receipt_path.read_text(encoding="utf-8"))
    assert result.exit_code == ExitCode.SUCCESS
    assert receipt["status"] == "PASS"
    assert receipt["immutability"]["database_unchanged"] is True
    assert receipt["immutability"]["alert_lifecycle_mutated"] is False
    assert receipt["immutability"]["report_generated"] is False
    assert receipt["bindings"]["database_before"] == receipt["bindings"]["database_after"]
    assert not (tmp_path / "execution.lock.json").exists()


def test_active_lock_returns_governed_exit_code_and_receipt(tmp_path: Path) -> None:
    _write_lock(tmp_path / "execution.lock.json", datetime.now(timezone.utc))
    result = ScheduledExecutionRunner(ROOT, runtime_root=tmp_path).run()
    receipt = json.loads(result.receipt_path.read_text(encoding="utf-8"))
    assert result.exit_code == ExitCode.ACTIVE_LOCK
    assert receipt["status"] == "BLOCKED"
    assert receipt["exit_code"] == 30


def test_invalid_profile_returns_configuration_code(tmp_path: Path) -> None:
    result = ScheduledExecutionRunner(ROOT, runtime_root=tmp_path).run(profile="INVALID")
    assert result.exit_code == ExitCode.CONFIGURATION_OR_CONTRACT_FAILURE


def test_report_failure_has_distinct_exit_code(tmp_path: Path, monkeypatch) -> None:
    runner = ScheduledExecutionRunner(ROOT, runtime_root=tmp_path)

    def fail() -> None:
        raise ReportBindingFailure("fixture")

    monkeypatch.setattr(runner, "_verify_report_binding", fail)
    result = runner.run()
    assert result.exit_code == ExitCode.REPORT_OR_QUERY_FAILURE


def test_manifest_chain_failure_has_distinct_exit_code(tmp_path: Path, monkeypatch) -> None:
    runner = ScheduledExecutionRunner(ROOT, runtime_root=tmp_path)

    def fail() -> None:
        raise ManifestChainFailure("fixture")

    monkeypatch.setattr(runner, "_verify_phase14_binding", fail)
    result = runner.run()
    assert result.exit_code == ExitCode.MANIFEST_CHAIN_FAILURE


def test_frozen_write_attempt_is_blocked_and_receipted(tmp_path: Path, monkeypatch) -> None:
    class FakeOrchestrator:
        def __init__(self, root: Path) -> None:
            pass

        def verify_frozen(self, *, generate_report: bool):
            raise FrozenEvidenceWriteError("fixture frozen path")

    monkeypatch.setattr(runner_module, "MonitoringOrchestrator", FakeOrchestrator)
    result = ScheduledExecutionRunner(ROOT, runtime_root=tmp_path).run()
    receipt = json.loads(result.receipt_path.read_text(encoding="utf-8"))
    assert result.exit_code == ExitCode.FROZEN_WRITE_ATTEMPT
    assert receipt["frozen_write_attempted"] is True
    assert receipt["frozen_write_blocked"] is True


def test_orchestrator_failure_releases_lock_and_writes_receipt(tmp_path: Path, monkeypatch) -> None:
    class FakeOrchestrator:
        def __init__(self, root: Path) -> None:
            pass

        def verify_frozen(self, *, generate_report: bool):
            raise RuntimeError("fixture orchestrator failure")

    monkeypatch.setattr(runner_module, "MonitoringOrchestrator", FakeOrchestrator)
    result = ScheduledExecutionRunner(ROOT, runtime_root=tmp_path).run()
    assert result.exit_code == ExitCode.ORCHESTRATION_FAILURE
    assert result.receipt_path.is_file()
    assert not (tmp_path / "execution.lock.json").exists()


def test_receipt_failure_uses_valid_emergency_receipt(tmp_path: Path, monkeypatch) -> None:
    import jsonschema

    def fail_write(path: Path, payload: dict) -> None:
        raise OSError("fixture receipt failure")

    monkeypatch.setattr(runner_module, "write_json_atomic", fail_write)
    result = ScheduledExecutionRunner(ROOT, runtime_root=tmp_path).run()
    receipt = json.loads(result.receipt_path.read_text(encoding="utf-8"))
    assert result.exit_code == ExitCode.RECEIPT_OR_LOGGING_FAILURE
    assert receipt["exit_code"] == 80
    assert receipt["status"] == "FAIL"
    assert receipt["execution_status"] == "FAIL"
    assert receipt["error_class"] == receipt["error"]["type"] == "OSError"
    assert receipt["error_message"] == receipt["error"]["message"] == "fixture receipt failure"
    schema = json.loads((ROOT / "schemas/scheduled_execution_receipt.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(receipt, schema)


def test_underlying_failure_plus_receipt_failure_has_one_consistent_terminal_state(
    tmp_path: Path, monkeypatch,
) -> None:
    class FakeOrchestrator:
        def __init__(self, root: Path) -> None:
            pass

        def verify_frozen(self, *, generate_report: bool):
            raise RuntimeError("fixture underlying failure")

    def fail_write(path: Path, payload: dict) -> None:
        raise OSError("fixture receipt failure after underlying failure")

    monkeypatch.setattr(runner_module, "MonitoringOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(runner_module, "write_json_atomic", fail_write)
    result = ScheduledExecutionRunner(ROOT, runtime_root=tmp_path).run()
    receipt = json.loads(result.receipt_path.read_text(encoding="utf-8"))
    assert result.exit_code == ExitCode.RECEIPT_OR_LOGGING_FAILURE
    assert receipt["status"] == receipt["execution_status"] == "FAIL"
    assert receipt["exit_code"] == 80
    assert receipt["error_class"] == receipt["error"]["type"] == "OSError"
    assert receipt["error_message"] == receipt["error"]["message"]


def test_logging_failure_returns_exit_80_and_preserves_valid_receipt(tmp_path: Path, monkeypatch) -> None:
    import jsonschema
    from credit_risk_monitoring.scheduling.receipts import AggregateEventLog

    def fail_append(self, record: dict[str, str]) -> None:
        raise OSError("fixture aggregate log failure")

    monkeypatch.setattr(AggregateEventLog, "_append", fail_append)
    result = ScheduledExecutionRunner(ROOT, runtime_root=tmp_path).run()
    receipt = json.loads(result.receipt_path.read_text(encoding="utf-8"))
    assert result.exit_code == ExitCode.RECEIPT_OR_LOGGING_FAILURE
    assert receipt["status"] == receipt["execution_status"] == "FAIL"
    assert receipt["exit_code"] == 80
    assert receipt["error_class"] == receipt["error"]["type"] == "OSError"
    assert receipt["error_message"] == receipt["error"]["message"] == "fixture aggregate log failure"
    schema = json.loads((ROOT / "schemas/scheduled_execution_receipt.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(receipt, schema)


def test_success_and_failure_receipts_conform_to_schema(tmp_path: Path) -> None:
    import jsonschema

    schema = json.loads((ROOT / "schemas/scheduled_execution_receipt.schema.json").read_text(encoding="utf-8"))
    success = ScheduledExecutionRunner(ROOT, runtime_root=tmp_path / "success").run()
    failure = ScheduledExecutionRunner(ROOT, runtime_root=tmp_path / "failure").run(profile="INVALID")
    for result in (success, failure):
        jsonschema.validate(json.loads(result.receipt_path.read_text(encoding="utf-8")), schema)


def test_receipt_contains_no_applicant_payload_fields(tmp_path: Path) -> None:
    result = ScheduledExecutionRunner(ROOT, runtime_root=tmp_path).run()
    receipt_text = result.receipt_path.read_text(encoding="utf-8").lower()
    for forbidden in ("sk_id_curr", "target", "applicant_record", "raw_prediction"):
        assert forbidden not in receipt_text
