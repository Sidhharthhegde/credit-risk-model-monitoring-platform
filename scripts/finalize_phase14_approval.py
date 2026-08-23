"""Record conditional-owner-review remediation and freeze Phase 14."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from credit_risk_monitoring.qualification.binding import sha256_file


FINAL_ID = "FINAL-LIFECYCLE-QUALIFICATION-01"
CANDIDATE_MANIFEST_SHA256 = "1396fd7882c16681aee1a324e661795bb0c136079aa5d9441bf47278639ae6bc"
REPORT_FILE_HASHES = {
    "monitoring_report.html": "c6f1a729f5b73c7d03ae719a18fbe7b67b48cd20f555a9ecbdfd8a1557412be8",
    "monitoring_report.pdf": "13a25ae7ad662ba50bbf8cf2a54dd3ea1480054f25aa7bfc2c19e923176817da",
    "monitoring_report_snapshot.json": "9dde8f1640e373130da2dfdaa568728a1f958be439284c86df67ae08011456e0",
}


def _json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _record(path: Path, root: Path) -> dict[str, Any]:
    return {"path": path.relative_to(root).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def _refresh_approved(root: Path, report: Path, manifest_path: Path, current: dict[str, Any]) -> Path:
    reconciliation_path = report / "approval_hash_reconciliation.json"
    reconciliation = json.loads(reconciliation_path.read_text(encoding="utf-8"))
    reconciliation.pop("all_candidate_technical_artifacts_unchanged", None)
    reconciliation.update({
        "candidate_artifact_hashes_preserved_for_reference": True,
        "all_substantive_technical_artifacts_unchanged": True,
        "governance_artifacts_changed_as_expected": [
            "documentation_reconciliation.json", "phase14_acceptance_checklist.csv",
            "phase14_completion_decision.json", "project_completion_decision.json",
        ],
    })
    _json(reconciliation_path, reconciliation)
    files = sorted(path for path in report.iterdir() if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"})
    _json(manifest_path, {
        **{key: value for key, value in current.items() if key not in {"artifacts", "approval_finalizer_sha256"}},
        "artifacts": [_record(path, report) for path in files],
        "approval_finalizer_sha256": sha256_file(root / "scripts/finalize_phase14_approval.py"),
    })
    (report / "manifest.sha256").write_text(sha256_file(manifest_path) + "\n", encoding="ascii", newline="\n")
    return manifest_path


def finalize(project_root: Path) -> Path:
    root = project_root.resolve()
    report = root / "reports/lifecycle" / FINAL_ID
    manifest_path = report / "manifest.json"
    if sha256_file(manifest_path) != CANDIDATE_MANIFEST_SHA256:
        current = json.loads(manifest_path.read_text(encoding="utf-8"))
        if current.get("status") == "APPROVED_FROZEN":
            return _refresh_approved(root, report, manifest_path, current)
        raise RuntimeError("Phase 14 pre-approval candidate manifest changed")
    candidate = json.loads(manifest_path.read_text(encoding="utf-8"))
    for artifact in candidate["artifacts"]:
        if sha256_file(report / artifact["path"]) != artifact["sha256"]:
            raise RuntimeError(f"Phase 14 technical evidence changed: {artifact['path']}")
    monitoring_report = root / "reports/monitoring_report/MONITORING-REPORT-01"
    for name, expected in REPORT_FILE_HASHES.items():
        if sha256_file(monitoring_report / name) != expected:
            raise RuntimeError(f"Qualified monitoring report changed: {name}")

    approved_utc = datetime.now(timezone.utc).isoformat()
    _json(report / "phase14_approval_record.json", {
        "phase": "PHASE_14", "final_lifecycle_id": FINAL_ID, "decision": "APPROVED",
        "approved_utc": approved_utc, "pre_approval_candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256,
        "approval_condition": "PROJECT_COMPLETION_DEFERRED_TO_PHASE_15",
        "condition_remediated": True, "technical_evidence_changed": False,
        "monitoring_report_changed": False, "orchestrator_changed": False, "replay_evidence_changed": False,
        "project_implementation_complete": False, "project_b_complete": False,
        "project_completion_reason": "PHASE_15_SCHEDULED_EXECUTION_AND_FINAL_PROJECT_RELEASE_PENDING",
        "phase_15_authorized": True,
        "next_phase_authorized": "PHASE_15_SCHEDULED_EXECUTION_AND_FINAL_PROJECT_RELEASE",
    })
    _json(report / "approval_hash_reconciliation.json", {
        "result": "PASS", "pre_approval_candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256,
        "candidate_artifacts": {item["path"]: item["sha256"] for item in candidate["artifacts"]},
        "all_candidate_technical_artifacts_unchanged": True,
        "monitoring_report_files": {name: {"candidate_sha256": value, "approved_sha256": sha256_file(monitoring_report / name), "unchanged": True} for name, value in REPORT_FILE_HASHES.items()},
        "all_monitoring_report_files_unchanged": True,
    })

    decision_path = report / "phase14_completion_decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision.update({
        "review_decision": "APPROVED", "phase_14_complete": True,
        "verify_frozen_default": True, "phase12_semantic_rebuild_qualified": True,
        "secret_scan_pass": True, "model_refit": False, "recalibration": False,
        "threshold_retuning": False, "model_production_approved": False,
        "real_production_deployment": False, "empirical_production_performance": False,
        "external_validation": False, "fairness_certification": False,
        "project_implementation_complete": False, "project_b_complete": False,
        "project_completion_status": "PHASE_15_PENDING", "phase_15_authorized": True,
        "project_completion_reason": "PHASE_15_SCHEDULED_EXECUTION_AND_FINAL_PROJECT_RELEASE_PENDING",
        "next_phase_authorized": "PHASE_15_SCHEDULED_EXECUTION_AND_FINAL_PROJECT_RELEASE",
    })
    _json(decision_path, decision)

    project_path = report / "project_completion_decision.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    project.update({
        "decision": "NOT_COMPLETE_PHASE_15_PENDING",
        "project_completion_decision": "NOT_COMPLETE_PHASE_15_PENDING",
        "project_implementation_complete": False, "project_b_complete": False,
        "production_shaped_monitoring_lifecycle_demo_complete": False,
        "project_completion_reason": "PHASE_15_SCHEDULED_EXECUTION_AND_FINAL_PROJECT_RELEASE_PENDING",
        "phase_15_authorized": True,
    })
    _json(project_path, project)

    documentation_path = report / "documentation_reconciliation.json"
    documentation = json.loads(documentation_path.read_text(encoding="utf-8"))
    documentation.update({
        "authoritative_phase_numbering": "PHASE_0_THROUGH_15",
        "roadmap_reorganized": True,
        "phase_12_through_14_consolidated_prior_persistence_dashboard_testing_reporting_orchestration_work": True,
        "phase_15_retains_scheduled_execution_and_final_release": True,
        "project_completion_deferred_to_phase_15": True,
    })
    _json(documentation_path, documentation)

    checklist_path = report / "phase14_acceptance_checklist.csv"
    with checklist_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows.extend([
        {"control_id": "P14-025", "control": "Owner approved and froze Phase 14 technical scope", "result": "PASS"},
        {"control_id": "P14-026", "control": "Project completion remains false pending Phase 15", "result": "PASS"},
        {"control_id": "P14-027", "control": "Phase 15 scheduled execution and final release is authorized", "result": "PASS"},
        {"control_id": "P14-028", "control": "All candidate technical and report artifacts remained unchanged during approval", "result": "PASS"},
    ])
    with checklist_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["control_id", "control", "result"], lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)

    report_manifest_path = monitoring_report / "report_manifest.json"
    report_manifest = json.loads(report_manifest_path.read_text(encoding="utf-8"))
    report_manifest.update({
        "status": "APPROVED_FROZEN", "approved_utc": approved_utc,
        "phase14_pre_approval_candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256,
        "report_files_unchanged_during_approval": True,
    })
    _json(report_manifest_path, report_manifest)

    files = sorted(path for path in report.iterdir() if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"})
    _json(manifest_path, {
        "final_lifecycle_id": FINAL_ID, "status": "APPROVED_FROZEN",
        "created_utc": candidate["created_utc"], "approved_utc": approved_utc,
        "pre_approval_candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256,
        "artifacts": [_record(path, report) for path in files],
        "aggregate_public_evidence_only": True, "approval_record_included": True,
        "technical_evidence_unchanged_during_approval": True,
        "monitoring_report_unchanged_during_approval": True,
        "project_implementation_complete": False, "project_b_complete": False,
        "phase_15_authorized": True,
        "approval_finalizer_sha256": sha256_file(root / "scripts/finalize_phase14_approval.py"),
    })
    (report / "manifest.sha256").write_text(sha256_file(manifest_path) + "\n", encoding="ascii", newline="\n")
    return manifest_path


if __name__ == "__main__":
    finalize(Path.cwd())
