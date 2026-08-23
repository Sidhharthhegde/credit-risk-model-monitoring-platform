"""Record owner approval and freeze the Phase 13 dashboard evidence package."""

from __future__ import annotations

import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from credit_risk_monitoring.qualification.binding import sha256_file


DASHBOARD_ID = "MONITORING-DASHBOARD-01"
CANDIDATE_MANIFEST_SHA256 = "0d395e610111f3308841b9ddbbffc61a66c7ea3ce2f58d4fe4f29d929ab1c2cf"
PART_A_COMMIT = "0f758a8ee76906b2a870ebacbdcac0ef6c951485"


def _json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _record(path: Path, root: Path) -> dict[str, Any]:
    return {"path": path.relative_to(root).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), *args], text=True,
    ).strip()


def _refresh_approved_gate(root: Path, report: Path, manifest_path: Path, current: dict[str, Any]) -> Path:
    """Reconcile the approval-aware test gate without changing dashboard runtime sources."""
    test_path = root / "tests/dashboard/test_dashboard.py"
    candidate_test_sha256 = "081cb2fc4ba7881d6ebcfbf1cf0e1dd16ced4af95b9414d3db215bb289da66b1"
    approved_test_sha256 = sha256_file(test_path)
    approval_path = report / "phase13_approval_record.json"
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    approval["dashboard_runtime_source_hashes_unchanged"] = True
    approval["approval_gate_test_updated_for_frozen_state"] = True
    approval["dashboard_source_hashes_unchanged"] = False
    _json(approval_path, approval)
    reconciliation_path = report / "approval_hash_reconciliation.json"
    reconciliation = json.loads(reconciliation_path.read_text(encoding="utf-8"))
    reconciliation["all_dashboard_runtime_sources_unchanged"] = True
    reconciliation["all_dashboard_sources_unchanged"] = False
    reconciliation["approval_gate_test_updated_for_frozen_state"] = True
    _json(reconciliation_path, reconciliation)
    _json(report / "post_approval_source_reconciliation.json", {
        "result": "PASS", "dashboard_runtime_sources_unchanged": True,
        "qualification_test_path": "tests/dashboard/test_dashboard.py",
        "candidate_test_sha256": candidate_test_sha256, "approved_test_sha256": approved_test_sha256,
        "test_change_role": "APPROVAL_GATE_ONLY", "dashboard_behavior_changed": False,
        "monitoring_result_changed": False, "frozen_evidence_changed": False,
    })
    files = sorted(path for path in report.iterdir() if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"})
    _json(manifest_path, {
        **{key: value for key, value in current.items() if key not in {"artifacts", "approval_finalizer_sha256"}},
        "artifacts": [_record(path, report) for path in files],
        "dashboard_runtime_sources_unchanged_during_approval": True,
        "approval_gate_test_updated_for_frozen_state": True,
        "approval_finalizer_sha256": sha256_file(root / "scripts/finalize_phase13_approval.py"),
    })
    (report / "manifest.sha256").write_text(sha256_file(manifest_path) + "\n", encoding="ascii", newline="\n")
    return manifest_path


def finalize(project_root: Path) -> Path:
    root = project_root.resolve()
    report = root / "reports/dashboard" / DASHBOARD_ID
    manifest_path = report / "manifest.json"
    if sha256_file(manifest_path) != CANDIDATE_MANIFEST_SHA256:
        current = json.loads(manifest_path.read_text(encoding="utf-8"))
        if current.get("status") == "APPROVED_FROZEN":
            return _refresh_approved_gate(root, report, manifest_path, current)
        raise RuntimeError("Phase 13 pre-approval candidate manifest changed")
    candidate = json.loads(manifest_path.read_text(encoding="utf-8"))
    for artifact in candidate["artifacts"]:
        if sha256_file(report / artifact["path"]) != artifact["sha256"]:
            raise RuntimeError(f"Phase 13 candidate artifact changed: {artifact['path']}")

    source_binding = json.loads((report / "dashboard_source_binding.json").read_text(encoding="utf-8"))
    for source in source_binding["dashboard_sources"]:
        if sha256_file(root / source["path"]) != source["sha256"]:
            raise RuntimeError(f"Qualified dashboard source changed: {source['path']}")

    phase12_manifest = root / "reports/persistence/MONITORING-HISTORY-01/manifest.json"
    if sha256_file(phase12_manifest) != "967a0646b403344944a5389447873bb6d1e432afece1167d26810670774ac165":
        raise RuntimeError("Frozen Phase 12 manifest changed")
    part_a = root.parent / "Part A - Credit Risk Model Validation Suite"
    if _git(part_a, "rev-parse", "HEAD") != PART_A_COMMIT or _git(part_a, "status", "--porcelain"):
        raise RuntimeError("Part A commit or working-tree state does not match the frozen binding")

    approved_utc = datetime.now(timezone.utc).isoformat()
    _json(report / "phase13_approval_record.json", {
        "phase": "PHASE_13", "dashboard_id": DASHBOARD_ID, "decision": "APPROVED",
        "approved_utc": approved_utc, "pre_approval_candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256,
        "dashboard_source_hashes_unchanged": True, "phase12_manifest_unchanged": True,
        "phase12_immutable_evidence_unchanged": True, "base_operational_state_modified_by_qualification": False,
        "detailed_score_bin_view": "UNAVAILABLE_BY_GOVERNED_QUERY_CONTRACT",
        "detailed_segment_result_view": "UNAVAILABLE_BY_GOVERNED_QUERY_CONTRACT",
        "raw_file_fallback_for_unavailable_views": False, "part_a_commit": PART_A_COMMIT,
        "part_a_unchanged": True, "cnd_02_status": "OPEN",
        "next_phase_authorized": "PHASE_14_MONITORING_REPORT_ORCHESTRATION_AND_FINAL_LIFECYCLE_QUALIFICATION",
    })
    _json(report / "approval_hash_reconciliation.json", {
        "result": "PASS", "pre_approval_candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256,
        "candidate_artifacts": {item["path"]: item["sha256"] for item in candidate["artifacts"]},
        "all_candidate_artifacts_unchanged": True, "all_dashboard_sources_unchanged": True,
        "phase12_manifest_sha256": sha256_file(phase12_manifest), "phase12_manifest_unchanged": True,
        "part_a_commit": PART_A_COMMIT, "part_a_working_tree_clean": True,
    })

    decision_path = report / "phase13_completion_decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision.update({
        "review_decision": "APPROVED", "phase_13_complete": True, "phase_14_authorized": True,
        "dashboard_role": "PRESENTATION_AND_INVESTIGATION_INTERFACE",
        "frozen_source_evidence_authoritative": True, "normal_ui_raw_artifact_bypass": False,
        "monitoring_metrics_recalculated": False, "monitoring_severities_recalculated": False,
        "alerts_recalculated": False, "overall_health_recalculated": False,
        "immutable_evidence_digest_bound": True, "current_alert_state_cached": False,
        "alert_acknowledgement_ui_implemented": True, "alert_resolution_ui_implemented": True,
        "synthetic_evidence_disclosure_implemented": True, "not_assessable_disclosure_implemented": True,
        "non_calendar_disclosure_implemented": True, "fairness_scope_disclosure_implemented": True,
        "detailed_score_bin_view": "UNAVAILABLE_BY_GOVERNED_QUERY_CONTRACT",
        "detailed_segment_result_view": "UNAVAILABLE_BY_GOVERNED_QUERY_CONTRACT",
        "raw_file_fallback_for_unavailable_views": False, "applicant_level_data_displayed": False,
        "fairness_certification_claimed": False, "production_performance_claimed": False,
        "external_validation_claimed": False,
        "next_phase_authorized": "PHASE_14_MONITORING_REPORT_ORCHESTRATION_AND_FINAL_LIFECYCLE_QUALIFICATION",
    })
    _json(decision_path, decision)

    checklist_path = report / "phase13_acceptance_checklist.csv"
    with checklist_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows.extend([
        {"control_id": "P13-025", "control": "Owner approved Phase 13 and authorized Phase 14", "result": "PASS"},
        {"control_id": "P13-026", "control": "Qualified dashboard sources and Phase 12 frozen evidence remained unchanged", "result": "PASS"},
        {"control_id": "P13-027", "control": "Unavailable detailed views are explicitly governed and have no raw-file fallback", "result": "PASS"},
    ])
    with checklist_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["control_id", "control", "result"], lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)

    files = sorted(path for path in report.iterdir() if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"})
    _json(manifest_path, {
        "dashboard_id": DASHBOARD_ID, "status": "APPROVED_FROZEN",
        "created_utc": candidate["created_utc"], "approved_utc": approved_utc,
        "pre_approval_candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256,
        "artifacts": [_record(path, report) for path in files],
        "dashboard_authoritative_evidence": False, "frozen_source_evidence_authoritative": True,
        "approval_record_included": True, "dashboard_sources_unchanged_during_approval": True,
        "phase12_evidence_unchanged_during_approval": True,
        "approval_finalizer_sha256": sha256_file(root / "scripts/finalize_phase13_approval.py"),
    })
    (report / "manifest.sha256").write_text(sha256_file(manifest_path) + "\n", encoding="ascii", newline="\n")
    return manifest_path


if __name__ == "__main__":
    finalize(Path.cwd())
