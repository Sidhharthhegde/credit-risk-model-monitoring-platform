"""Finalize approved Phase 7 evidence without changing calculated drift results."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from credit_risk_monitoring.qualification.binding import sha256_file


MONITORING_ID = "FEATURE-DRIFT-MONITORING-01"
CANDIDATE_MANIFEST_SHA256 = "15e0d9582113d79c923b36433a5d8733c059a77628c21712243a8338ee578ea6"
FROZEN_UPSTREAM = {
    "reports/reference/REFERENCE-MATERIALIZATION-01/manifest.json": "8fbf4490d78d8c36e89af618cc0bbece4b539feae5321889647037b4b7de2ddc",
    "reports/simulation/SIMULATION-SCENARIO-SET-01/manifest.json": "0681cf14053b82cc7e9da87ce7ca4a227d575a52821de3ab040be9ee445184a5",
    "reports/monitoring/DATA-QUALITY-CONTROL-01/manifest.json": "106033382085f39d838c28eb93cfcf3daab1a1e9c8a3b8217645c60adcec500b",
}
CALCULATED_RESULTS = {
    "feature_drift_results.parquet": "bc83f800599792eb9a51b0eb4ca29cc8bd9e6acac404775bba2336d7639dc071",
    "feature_psi_bin_contributions.parquet": "5363167d28eeb420655b20af5189aeea3be9f170fccb07e1f5d5a4c71d91e60a",
    "numeric_drift_diagnostics.parquet": "c9999dfd708f819a53f06a842eed4b4aedb0617ba1e23978186c53ce671c46d4",
    "categorical_drift_diagnostics.parquet": "dd5762eeeee8f76cdefd4f4484a6d9cdad6983d9f5a762dfb12b015e804594f5",
}


def _json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _record(path: Path, root: Path) -> dict[str, Any]:
    return {"path": path.relative_to(root).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def finalize(project_root: Path) -> Path:
    project_root = project_root.resolve()
    report = project_root / "reports/monitoring" / MONITORING_ID
    manifest_path = report / "manifest.json"
    if sha256_file(manifest_path) != CANDIDATE_MANIFEST_SHA256:
        raise RuntimeError("Phase 7 candidate manifest changed")
    candidate = json.loads(manifest_path.read_text(encoding="utf-8"))
    for relative, expected in FROZEN_UPSTREAM.items():
        if sha256_file(project_root / relative) != expected:
            raise RuntimeError(f"Frozen upstream manifest changed: {relative}")
    result_hashes = {}
    for name, expected in CALCULATED_RESULTS.items():
        actual = sha256_file(report / name)
        if actual != expected:
            raise RuntimeError(f"Calculated Phase 7 result changed: {name}")
        result_hashes[name] = {"candidate_sha256": expected, "approved_sha256": actual, "unchanged": True}

    approved_utc = datetime.now(timezone.utc).isoformat()
    contract_path = project_root / "contracts/feature_drift_monitoring_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    _json(report / "control_registry.json", {
        "monitoring_id": MONITORING_ID, "status": "APPROVED_FROZEN",
        "contract_sha256": sha256_file(contract_path), "metrics": contract["metrics"],
    })
    _json(report / "population_drift_component_semantics.json", {
        "status": "APPROVED_FROZEN",
        "field": "population_drift_state",
        "derivation": "MAXIMUM_ELIGIBLE_FEATURE_PSI_SEVERITY",
        "meaning": "POPULATION_DRIFT_COMPONENT_STATUS_ONLY",
        "is_overall_model_health": False,
        "is_alert_lifecycle_event": False,
        "independently_generates_alert": False,
    })
    _json(report / "phase7_approval_record.json", {
        "phase": "PHASE_7", "monitoring_id": MONITORING_ID, "decision": "APPROVED",
        "approved_utc": approved_utc, "candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256,
        "calculated_drift_results_changed": False, "cnd_02_status": "OPEN",
        "next_phase_authorized": "PHASE_8_PREDICTION_AND_THRESHOLD_OUTPUT_MONITORING",
    })
    _json(report / "approval_hash_reconciliation.json", {
        "result": "PASS", "candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256,
        "calculated_results": result_hashes, "all_calculated_results_unchanged": True,
        "frozen_upstream_manifests": FROZEN_UPSTREAM, "all_upstream_manifests_unchanged": True,
        "scenario_artifacts_modified": False, "part_a_modified": False,
    })
    checklist_path = report / "phase7_acceptance_checklist.csv"
    with checklist_path.open(encoding="utf-8", newline="") as handle:
        checklist = list(csv.DictReader(handle))
    checklist[-1] = {"control_id": checklist[-1]["control_id"], "control": "Owner approved Phase 7 and authorized Phase 8", "result": "PASS"}
    with checklist_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["control_id", "control", "result"], lineterminator="\n")
        writer.writeheader(); writer.writerows(checklist)
    _json(report / "phase7_completion_decision.json", {
        "phase": "PHASE_7", "phase_name": "FEATURE_AND_POPULATION_DRIFT_MONITORING",
        "monitoring_id": MONITORING_ID, "review_decision": "APPROVED", "technical_qualification": "PASS",
        "phase_7_complete": True, "eligible_artifact_count": 6, "excluded_artifact_count": 2,
        "feature_psi_calculated": True, "feature_psi_result_count": 1056,
        "numeric_ks_calculated": True, "numeric_wasserstein_calculated": True, "numeric_diagnostic_count": 786,
        "categorical_chi_square_calculated": True, "categorical_diagnostic_count": 270,
        "all_176_features_accounted_for": True, "frozen_reference_bins_used": True, "rebucketing_performed": False,
        "psi_bin_reconciliation_verified": True, "drift_reproducibility_verified": True,
        "p_values_drive_severity": False, "shap_tiers_drive_severity": False,
        "population_drift_state_is_component_only": True, "cnd_02_status": "OPEN",
        "score_monitoring_results_calculated": False, "performance_results_calculated": False,
        "calibration_results_calculated": False, "subgroup_results_calculated": False,
        "monitoring_alerts_generated": False, "overall_model_health_calculated": False,
        "next_phase_authorized": "PHASE_8_PREDICTION_AND_THRESHOLD_OUTPUT_MONITORING", "phase_8_authorized": True,
    })
    execution_path = report / "execution_source_manifest.json"
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    sources = [
        contract_path, project_root / "src/credit_risk_monitoring/drift/engine.py",
        project_root / "src/credit_risk_monitoring/drift/__init__.py",
        project_root / "scripts/run_phase7_monitoring.py", project_root / "scripts/finalize_phase7_approval.py",
    ]
    execution["implementation_sources"] = [{"path": path.relative_to(project_root).as_posix(), "sha256": sha256_file(path)} for path in sources]
    execution["approval_finalizer_included"] = True
    _json(execution_path, execution)
    artifacts = sorted(path for path in report.iterdir() if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"})
    final_manifest = {
        "monitoring_id": MONITORING_ID, "status": "APPROVED_FROZEN",
        "created_utc": candidate["created_utc"], "approved_utc": approved_utc,
        "candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256,
        "artifacts": [_record(path, report) for path in artifacts], "aggregate_results_only": True,
        "row_level_identifiers_included": False, "alerts_included": False, "approval_record_included": True,
        "calculated_results_unchanged_during_approval": True,
    }
    _json(manifest_path, final_manifest)
    (report / "manifest.sha256").write_text(sha256_file(manifest_path) + "\n", encoding="ascii", newline="\n")
    return manifest_path


if __name__ == "__main__":
    finalize(Path.cwd())
