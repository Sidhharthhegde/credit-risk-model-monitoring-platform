from __future__ import annotations

from pathlib import Path


class FrozenEvidenceWriteError(RuntimeError):
    pass


def outcome_stage_status(*, outcomes_available: bool, synthetic: bool) -> str:
    if not outcomes_available:
        return "SKIPPED_NOT_ASSESSABLE_OUTCOME_NOT_AVAILABLE"
    return "EXECUTED_SYNTHETIC_SCENARIO_EVIDENCE" if synthetic else "EXECUTED_EMPIRICAL_EVIDENCE"


def scoring_gate(*, hard_fail: bool, source_authorized: bool) -> dict[str, object]:
    if hard_fail:
        return {"technical_scoring": False, "authoritative_use": False, "state": "BLOCKED_HARD_GATE"}
    if not source_authorized:
        return {"technical_scoring": True, "authoritative_use": False, "state": "BLOCKED_SOURCE_GOVERNANCE"}
    return {"technical_scoring": True, "authoritative_use": True, "state": "AUTHORIZED"}


def guard_output_path(project_root: Path, candidate: Path, frozen_roots: list[str], permitted_roots: list[str]) -> None:
    root = project_root.resolve()
    target = candidate.resolve()
    permitted = [(root / item).resolve() for item in permitted_roots]
    if any(target == item or item in target.parents for item in permitted):
        return
    frozen = [(root / item).resolve() for item in frozen_roots]
    if any(target == item or item in target.parents for item in frozen):
        raise FrozenEvidenceWriteError(f"HARD_FAIL_FROZEN_EVIDENCE_WRITE_ATTEMPT: {target}")
    raise FrozenEvidenceWriteError(f"UNAPPROVED_ORCHESTRATION_OUTPUT_PATH: {target}")
