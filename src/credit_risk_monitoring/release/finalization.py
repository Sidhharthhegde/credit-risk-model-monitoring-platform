"""Owner-approved Phase 15 and Project B release finalization."""

from __future__ import annotations

import csv
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from credit_risk_monitoring.history.digest import semantic_database_manifest
from credit_risk_monitoring.history.store import connect_history
from credit_risk_monitoring.qualification.binding import sha256_file


PROJECT_RELEASE_ID = "PROJECT-RELEASE-01"
PROJECT_COMPLETION_ID = "PROJECT-COMPLETION-01"
PRE_FINALIZATION_CANDIDATE_SHA256 = "d64a30657cba57beec79d0b5ff43c5f3726ce91ca4bb2bcd190d24f19abfcf0a"
APPROVED_CASEBOOK_SHA256 = "204bc4c9e910aee901b1354678ec59d51d1defeb6893a021b3e9400790ec9835"
APPROVED_ALERT_EVENT_LEDGER_SHA256 = "6e5c8bda305d5111e94ea4f8cb511aff7cf6c3823361ba1097d83c3fa05ea734"
APPROVED_PHASE12_DATABASE_SEMANTIC_SHA256 = "48eb52d1596199abd010c42d7348a73eda80b5969805a73729897a72fbdf7900"
RELEASE_VERSION = "1.0.0"
RELEASE_TAG = "model-monitoring-platform-v1.0.0"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _read_json_without_duplicate_members(path: Path) -> dict[str, Any]:
    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        counts = Counter(key for key, _ in pairs)
        duplicates = sorted(key for key, count in counts.items() if count > 1)
        if duplicates:
            raise RuntimeError(f"Duplicate JSON members in {path}: {duplicates}")
        return dict(pairs)

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs_hook)


def _artifact(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _git_status(root: Path) -> str:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root), "status", "--porcelain"],
        text=True,
    ).strip()


def _validate_candidate(report: Path, manifest_path: Path) -> dict[str, Any]:
    if sha256_file(manifest_path) != PRE_FINALIZATION_CANDIDATE_SHA256:
        raise RuntimeError("Phase 15 pre-finalization candidate manifest changed")
    candidate = _read_json_without_duplicate_members(manifest_path)
    for item in candidate["artifacts"]:
        artifact_path = report / item["path"]
        if sha256_file(artifact_path) != item["sha256"]:
            raise RuntimeError(f"Phase 15 candidate artifact changed: {item['path']}")
    return candidate


def _validate_frozen_boundaries(root: Path) -> dict[str, Any]:
    phase_chain_path = root / "reports/release" / PROJECT_RELEASE_ID / "phase_manifest_chain_0_14_reconciliation.json"
    phase_chain = _read_json_without_duplicate_members(phase_chain_path)
    if not phase_chain.get("all_match"):
        raise RuntimeError("Phase 0-14 reconciliation is not passing")
    for item in phase_chain["phases"]:
        if sha256_file(root / item["path"]) != item["sha256"]:
            raise RuntimeError(f"Frozen Phase {item['phase']} manifest changed")

    casebook_manifest = root / "reports/investigation/INVESTIGATION-CASEBOOK-01/manifest.json"
    if sha256_file(casebook_manifest) != APPROVED_CASEBOOK_SHA256:
        raise RuntimeError("Approved investigation casebook manifest changed")

    part_a = root.parent / "Part A - Credit Risk Model Validation Suite"
    if _git_status(part_a):
        raise RuntimeError("Part A working tree is not clean")

    contract = _read_json_without_duplicate_members(root / "contracts/model_risk_investigation_contract.json")
    connection = connect_history(root / contract["frozen_bindings"]["phase12_database_path"], read_only=True)
    try:
        database = semantic_database_manifest(connection)
    finally:
        connection.close()
    if database["database_semantic_sha256"] != APPROVED_PHASE12_DATABASE_SEMANTIC_SHA256:
        raise RuntimeError("Phase 12 operational database semantic digest changed")
    alert_events = database["tables"]["alert_events"]
    if alert_events["semantic_sha256"] != APPROVED_ALERT_EVENT_LEDGER_SHA256:
        raise RuntimeError("Phase 12 alert-event ledger changed")
    return {
        "phase_0_through_14_manifest_chain_unchanged": True,
        "part_a_working_tree_clean": True,
        "investigation_casebook_digest_stable": True,
        "alert_event_ledger_unchanged": True,
        "alert_event_ledger_sha256": alert_events["semantic_sha256"],
        "alert_event_count": alert_events["row_count"],
        "phase12_database_semantic_sha256": database["database_semantic_sha256"],
    }


def _approved_utc(report: Path) -> str:
    approval_path = report / "phase15_owner_approval_record.json"
    if approval_path.is_file():
        approval = _read_json_without_duplicate_members(approval_path)
        if approval.get("pre_finalization_candidate_manifest_sha256") != PRE_FINALIZATION_CANDIDATE_SHA256:
            raise RuntimeError("Existing Phase 15 approval record binds a different candidate")
        return str(approval["approved_utc"])
    return datetime.now(timezone.utc).isoformat()


def _write_final_state(root: Path, report: Path, approved_utc: str, integrity: dict[str, Any]) -> None:
    contract_path = root / "contracts/final_project_release_contract.json"
    contract = _read_json_without_duplicate_members(contract_path)
    contract["status"] = "APPROVED_FROZEN"
    contract["release"].update({
        "approved_tag": RELEASE_TAG,
        "owner_release_authorized": True,
        "remote_release_authorized": True,
        "publication_evidence_location": "ANNOTATED_GIT_TAG_AND_GITHUB_RELEASE",
    })
    contract["approval_gate"].update({
        "candidate_status": "SUPERSEDED_BY_APPROVED_FROZEN_RELEASE",
        "owner_completion_decision": "APPROVED",
        "owner_approval_recorded": True,
        "phase_15_complete": True,
        "project_complete": True,
    })
    _write_json(contract_path, contract)
    _write_json(report / "final_project_release_contract_snapshot.json", contract)

    _write_json(report / "phase15_owner_approval_record.json", {
        "approved_by": "Sidharth Ravindra Hegde",
        "approved_scope": "PHASE_15_AND_PROJECT_B_OWNER_COMPLETION_GATE",
        "approved_utc": approved_utc,
        "decision": "APPROVED",
        "investigation_assessment_authority": "APPROVED_AUTHORITATIVE_INVESTIGATION_RECORD",
        "investigation_casebook_manifest_sha256": APPROVED_CASEBOOK_SHA256,
        "pre_finalization_candidate_manifest_sha256": PRE_FINALIZATION_CANDIDATE_SHA256,
        "project_completion_id": PROJECT_COMPLETION_ID,
        "project_release_id": PROJECT_RELEASE_ID,
        "release_tag_authorized": RELEASE_TAG,
        "residual_conditions_retained": ["CND-02_OPEN", "THRESHOLD_BOUNDARY_DENSITY_CONTROLLED_DEFERRED"],
        "substantive_feature_blockers_remaining": False,
    })
    _write_json(report / "final_integrity_attestation.json", {
        **integrity,
        "casebook_manifest_sha256": APPROVED_CASEBOOK_SHA256,
        "monitoring_recalculated": False,
        "model_scored": False,
        "phase_0_through_14_writes_performed": False,
        "result": "PASS",
    })

    decision = _read_json_without_duplicate_members(report / "phase15_completion_decision.json")
    decision.update({
        "decision": "APPROVED_FROZEN",
        "owner_approval_recorded": True,
        "owner_approval_record": "phase15_owner_approval_record.json",
        "phase_15_complete": True,
        "project_implementation_complete": True,
        "project_b_complete": True,
        "project_completion_status": "COMPLETE",
        "release_version": RELEASE_VERSION,
        "release_tag_authorized": True,
        "release_tag_name": RELEASE_TAG,
        "release_tag_created_at_decision_time": False,
        "release_publication_evidence": "ANNOTATED_GIT_TAG_AND_GITHUB_RELEASE",
        "pre_finalization_candidate_manifest_sha256": PRE_FINALIZATION_CANDIDATE_SHA256,
        "cnd_02_status": "OPEN",
        "threshold_boundary_density_status": "CONTROLLED_DEFERRED",
    })
    decision.pop("release_tag_created", None)
    _write_json(report / "phase15_completion_decision.json", decision)

    _write_json(report / "project_completion_decision.json", {
        "cnd_02_status": "OPEN",
        "decision": "APPROVED_COMPLETE",
        "external_validation": False,
        "production_deployment": False,
        "project_b_complete": True,
        "project_completion_id": PROJECT_COMPLETION_ID,
        "project_completion_status": "COMPLETE",
        "project_implementation_complete": True,
        "release_version": RELEASE_VERSION,
        "residual_conditions_preserved": True,
        "threshold_boundary_density_status": "CONTROLLED_DEFERRED",
    })

    chain = _read_json_without_duplicate_members(report / "phase_manifest_chain_0_14_reconciliation.json")
    _write_json(report / "phase_manifest_chain_0_15.json", {
        "candidate_chain_reconciliation": "PASS",
        "final_owner_approved_chain_reconciliation": "PASS",
        "phase_15": {
            "final_manifest_path": "reports/release/PROJECT-RELEASE-01/manifest.json",
            "investigation_assessment_authority": "APPROVED_AUTHORITATIVE_INVESTIGATION_RECORD",
            "investigation_casebook_manifest_sha256": APPROVED_CASEBOOK_SHA256,
            "owner_approval_recorded": True,
            "pre_finalization_candidate_manifest_sha256": PRE_FINALIZATION_CANDIDATE_SHA256,
            "release_tag": RELEASE_TAG,
            "status": "APPROVED_FROZEN",
        },
        "phases_0_through_14": chain["phases"],
    })

    checklist_path = report / "phase15_acceptance_checklist.csv"
    with checklist_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if row["control"] == "OWNER_APPROVAL":
            row["status"] = "PASS"
        elif row["control"] == "FINAL_TAG_AND_REMOTE_RELEASE":
            row["control"] = "FINAL_TAG_AND_REMOTE_RELEASE_AUTHORIZED_POST_COMMIT"
            row["status"] = "PASS"
    with checklist_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["control", "status"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    summary = _read_json_without_duplicate_members(report / "release_candidate_summary.json")
    summary.update({
        "approved_utc": approved_utc,
        "candidate_manifest_sha256": PRE_FINALIZATION_CANDIDATE_SHA256,
        "owner_approval_recorded": True,
        "release_tag": RELEASE_TAG,
        "status": "APPROVED_FROZEN",
        "tag_and_remote_release_authorized_post_commit": True,
    })
    summary.pop("candidate_tag", None)
    summary.pop("remote_release_created", None)
    summary.pop("tag_created", None)
    _write_json(report / "release_candidate_summary.json", summary)

    documentation = _read_json_without_duplicate_members(report / "final_documentation_reconciliation.json")
    documentation.update({
        "implementation_plan_version": "1.0.0",
        "implementation_plan_reconciled_to_completion": True,
        "owner_completion_gate": "APPROVED",
        "phase_15_status": "APPROVED_FROZEN",
        "project_b_complete": True,
        "release_version": RELEASE_VERSION,
        "result": "PASS",
    })
    _write_json(report / "final_documentation_reconciliation.json", documentation)


def finalize_phase15(root: Path) -> str:
    """Finalize the owner-approved Phase 15 state without mutating upstream evidence."""
    root = root.resolve()
    report = root / "reports/release" / PROJECT_RELEASE_ID
    manifest_path = report / "manifest.json"
    current = _read_json_without_duplicate_members(manifest_path)
    current_digest = sha256_file(manifest_path)
    if current_digest == PRE_FINALIZATION_CANDIDATE_SHA256:
        _validate_candidate(report, manifest_path)
    elif not (
        current.get("status") == "APPROVED_FROZEN"
        and current.get("pre_finalization_candidate_manifest_sha256") == PRE_FINALIZATION_CANDIDATE_SHA256
    ):
        raise RuntimeError("Phase 15 manifest is neither the approved candidate nor its frozen successor")

    integrity = _validate_frozen_boundaries(root)
    approved_utc = _approved_utc(report)
    _write_final_state(root, report, approved_utc, integrity)

    evidence_files = sorted(
        path for path in report.iterdir()
        if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"}
    )
    manifest = {
        "approved_utc": approved_utc,
        "artifacts": [_artifact(path, report) for path in evidence_files],
        "cnd_02_status": "OPEN",
        "investigation_assessment_authority": "APPROVED_AUTHORITATIVE_INVESTIGATION_RECORD",
        "investigation_casebook_manifest_sha256": APPROVED_CASEBOOK_SHA256,
        "owner_approval_recorded": True,
        "owner_approval_required": False,
        "phase_0_through_14_read_only": True,
        "phase_15_complete": True,
        "pre_finalization_candidate_manifest_sha256": PRE_FINALIZATION_CANDIDATE_SHA256,
        "project_b_complete": True,
        "project_completion_id": PROJECT_COMPLETION_ID,
        "project_implementation_complete": True,
        "project_release_id": PROJECT_RELEASE_ID,
        "release_publication_evidence": "ANNOTATED_GIT_TAG_AND_GITHUB_RELEASE",
        "release_tag": RELEASE_TAG,
        "release_tag_authorized": True,
        "release_version": RELEASE_VERSION,
        "status": "APPROVED_FROZEN",
        "threshold_boundary_density_status": "CONTROLLED_DEFERRED",
        "approval_finalizer_sha256": sha256_file(root / "src/credit_risk_monitoring/release/finalization.py"),
    }
    _write_json(manifest_path, manifest)
    digest = sha256_file(manifest_path)
    (report / "manifest.sha256").write_text(digest + "\n", encoding="ascii", newline="\n")
    return digest
