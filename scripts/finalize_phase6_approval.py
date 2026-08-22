"""Finalize the approved Phase 6 evidence without changing calculated DQ metrics."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from credit_risk_monitoring.qualification.binding import sha256_file


CONTROL_ID = "DATA-QUALITY-CONTROL-01"
PHASE5_MANIFEST_SHA256 = "0681cf14053b82cc7e9da87ce7ca4a227d575a52821de3ab040be9ee445184a5"
CONDITIONAL_REVIEW_CANDIDATE_MANIFEST_SHA256 = "b573494f1ea4b5cf3d22de82972b0c3b71c5d165aa35795759362f974a5afe2f"
PRE_REMEDIATION_METRIC_HASHES = {
    "categorical_novelty_results.parquet": "fd483110b64f30eb00c2dfe0c4fc69fdc1f69cfa6d1a8a8901dd38ffb8f8547c",
    "completeness_results.parquet": "3a9ef422cc1a9b7cdd8ce631196d95214cddc18bf52c57819de3e8caf1b3f107",
    "reference_range_diagnostics.parquet": "78cceacfb16234232d8980e3f32c0b1973a00a3a3e6b34022c21c63137740dc5",
    "validity_results.parquet": "f0a0434eee803b44be00f0a5864a88ae6595fc4eb37e9751beae1cb9c163b420",
}


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def finalize(project_root: Path) -> Path:
    project_root = project_root.resolve()
    report = project_root / "reports" / "monitoring" / CONTROL_ID
    manifest_path = report / "manifest.json"
    candidate_manifest_sha256 = sha256_file(manifest_path)
    candidate = json.loads(manifest_path.read_text(encoding="utf-8"))
    if candidate["status"] != "QUALIFIED_PENDING_REVIEW":
        raise RuntimeError("Phase 6 candidate is not awaiting approval")

    metric_reconciliation = {}
    for name, expected in PRE_REMEDIATION_METRIC_HASHES.items():
        actual = sha256_file(report / name)
        if actual != expected:
            raise RuntimeError(f"Calculated DQ evidence changed: {name}")
        metric_reconciliation[name] = {
            "pre_remediation_sha256": expected,
            "post_remediation_sha256": actual,
            "unchanged": True,
        }

    phase5_manifest_path = project_root / "reports" / "simulation" / "SIMULATION-SCENARIO-SET-01" / "manifest.json"
    if sha256_file(phase5_manifest_path) != PHASE5_MANIFEST_SHA256:
        raise RuntimeError("Frozen Phase 5 manifest changed")
    phase5 = json.loads(phase5_manifest_path.read_text(encoding="utf-8"))
    scenario_root = project_root / phase5["local_artifact_root"]
    local_reconciliation = {}
    for relative, expected in phase5["local_manifests"].items():
        actual = sha256_file(scenario_root / relative / "manifest.json")
        if actual != expected:
            raise RuntimeError(f"Frozen Phase 5 scenario manifest changed: {relative}")
        local_reconciliation[relative] = {"expected_sha256": expected, "actual_sha256": actual, "unchanged": True}

    source = json.loads((report / "source_control_results.json").read_text(encoding="utf-8"))["results"]
    if len(source) != 16:
        raise RuntimeError("Expected two source controls for each of eight artifacts")
    availability = [row for row in source if row["control_id"] == "DQ-SOURCE-AVAILABILITY-01"]
    authority = [row for row in source if row["control_id"] == "DQ-SOURCE-AUTHORITY-01"]
    if len(availability) != 8 or any(row["control_role"] != "DIRECT" for row in availability):
        raise RuntimeError("Source availability taxonomy is not governed")
    if len(authority) != 8 or any(row["control_role"] != "HARD_GATE" for row in authority):
        raise RuntimeError("Source authority taxonomy is not governed")

    approved_utc = datetime.now(timezone.utc).isoformat()
    contract_path = project_root / "contracts" / "data_quality_monitoring_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    registry_path = report / "control_registry.json"
    _write_json(registry_path, {
        "control_id": CONTROL_ID,
        "status": "APPROVED_FROZEN",
        "contract_sha256": sha256_file(contract_path),
        "controls": contract["controls"],
    })

    checklist_path = report / "phase6_acceptance_checklist.csv"
    with checklist_path.open(encoding="utf-8", newline="") as handle:
        checklist = list(csv.DictReader(handle))
    checklist[-1] = {
        "control_id": checklist[-1]["control_id"],
        "control": "Protocol owner approved Phase 6 after source-control taxonomy remediation",
        "result": "PASS",
    }
    with checklist_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["control_id", "control", "result"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(checklist)

    _write_json(report / "conditional_remediation_hash_reconciliation.json", {
        "result": "PASS",
        "remediation_scope": "CONTROL_CONTRACT_AND_EVIDENCE_TAXONOMY_ONLY",
        "pre_approval_candidate_manifest_sha256": candidate_manifest_sha256,
        "conditional_review_candidate_manifest_sha256": CONDITIONAL_REVIEW_CANDIDATE_MANIFEST_SHA256,
        "dq_metric_artifacts": metric_reconciliation,
        "all_dq_metric_artifacts_unchanged": True,
        "phase5_manifest_sha256": PHASE5_MANIFEST_SHA256,
        "phase5_local_manifests": local_reconciliation,
        "all_phase5_local_manifests_unchanged": True,
        "scenario_data_or_semantic_content_modified": False,
    })
    _write_json(report / "phase6_approval_record.json", {
        "phase": "PHASE_6",
        "control_id": CONTROL_ID,
        "decision": "APPROVED",
        "approved_utc": approved_utc,
        "conditional_review_candidate_manifest_sha256": CONDITIONAL_REVIEW_CANDIDATE_MANIFEST_SHA256,
        "conditional_blocker": "COMPOSITE_SOURCE_CONTROL_ROLE",
        "remediation": {
            "availability_control_id": "DQ-SOURCE-AVAILABILITY-01",
            "availability_control_role": "DIRECT",
            "authority_control_id": "DQ-SOURCE-AUTHORITY-01",
            "authority_control_role": "HARD_GATE",
        },
        "actual_dq_findings_changed": False,
        "cnd_02_status": "OPEN",
        "next_phase_authorized": "PHASE_7_FEATURE_AND_POPULATION_DRIFT_MONITORING",
    })
    _write_json(report / "phase6_completion_decision.json", {
        "phase": "PHASE_6",
        "control_id": CONTROL_ID,
        "review_decision": "APPROVED",
        "technical_qualification": "PASS",
        "phase_6_complete": True,
        "data_quality_engine_qualified": True,
        "input_control_engine_qualified": True,
        "schema_controls_executed": True,
        "grain_controls_executed": True,
        "completeness_controls_executed": True,
        "validity_controls_executed": True,
        "novelty_controls_executed": True,
        "source_controls_executed": True,
        "m05_hard_fail_verified": True,
        "m05_source_availability_verified": True,
        "m05_source_authority_gate_verified": True,
        "cnd_02_status": "OPEN",
        "dq_monitoring_results_calculated": True,
        "feature_drift_results_calculated": False,
        "score_monitoring_results_calculated": False,
        "performance_results_calculated": False,
        "calibration_results_calculated": False,
        "subgroup_results_calculated": False,
        "monitoring_alerts_generated": False,
        "overall_model_health_calculated": False,
        "next_phase_authorized": "PHASE_7_FEATURE_AND_POPULATION_DRIFT_MONITORING",
        "phase_7_authorized": True,
    })

    execution_path = report / "execution_source_manifest.json"
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    sources = [
        contract_path,
        project_root / "src" / "credit_risk_monitoring" / "data_quality" / "engine.py",
        project_root / "src" / "credit_risk_monitoring" / "data_quality" / "__init__.py",
        project_root / "scripts" / "run_phase6_monitoring.py",
        project_root / "scripts" / "finalize_phase6_approval.py",
    ]
    execution["implementation_sources"] = [
        {"path": path.relative_to(project_root).as_posix(), "sha256": sha256_file(path)} for path in sources
    ]
    execution["approval_finalizer_included"] = True
    _write_json(execution_path, execution)

    artifacts = sorted(
        path for path in report.iterdir()
        if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"}
    )
    final_manifest = {
        "control_id": CONTROL_ID,
        "status": "APPROVED_FROZEN",
        "created_utc": candidate["created_utc"],
        "approved_utc": approved_utc,
        "pre_approval_candidate_manifest_sha256": candidate_manifest_sha256,
        "artifacts": [_record(path, report) for path in artifacts],
        "aggregate_results_only": True,
        "row_level_offenders_included": False,
        "alerts_included": False,
        "approval_record_included": True,
        "dq_metric_artifacts_unchanged_during_remediation": True,
        "phase5_scenario_artifacts_unchanged": True,
    }
    _write_json(manifest_path, final_manifest)
    (report / "manifest.sha256").write_text(sha256_file(manifest_path) + "\n", encoding="ascii", newline="\n")
    return manifest_path


if __name__ == "__main__":
    finalize(Path.cwd())
