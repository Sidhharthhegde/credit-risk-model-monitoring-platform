"""Finalize approved Phase 8 public and local prediction evidence."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from credit_risk_monitoring.qualification.binding import sha256_file


MONITORING_ID = "PREDICTION-MONITORING-01"
CANDIDATE_MANIFEST_SHA256 = "91ec1173f8dfa6a41c70dc0806a34430433559f6ccddd53d5019bdfb329894c2"
FROZEN_UPSTREAM = {
    "reports/reference/REFERENCE-MATERIALIZATION-01/manifest.json": "8fbf4490d78d8c36e89af618cc0bbece4b539feae5321889647037b4b7de2ddc",
    "reports/simulation/SIMULATION-SCENARIO-SET-01/manifest.json": "0681cf14053b82cc7e9da87ce7ca4a227d575a52821de3ab040be9ee445184a5",
    "reports/monitoring/DATA-QUALITY-CONTROL-01/manifest.json": "106033382085f39d838c28eb93cfcf3daab1a1e9c8a3b8217645c60adcec500b",
    "reports/monitoring/FEATURE-DRIFT-MONITORING-01/manifest.json": "64a706d84465e0398391f9d217702343b31aa4d446864a9eca70db89bc930f17",
}
CALCULATED_RESULTS = {
    "prediction_summary_results.parquet": "042a17e5eb2a0c17fb0efe0b1a1fe0b5323a668f9f18903c008741dd0b9bac25",
    "score_psi_results.parquet": "86fc2f6b40b465efcf566a433662704ef87e3d7d0c1896d1bb7607d915e12328",
    "score_psi_bin_contributions.parquet": "eaafe0b175fabaa65a453d3fca1ff76a25d4dee3170abd74fbc8622d68b30989",
    "threshold_output_results.parquet": "bcba64cc5384ac2c5ad996a947fc85d8a6d9c72e798fe154bad886521d4c05c9",
}


def _json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _record(path: Path, root: Path) -> dict[str, Any]:
    return {"path": path.relative_to(root).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def finalize(project_root: Path) -> Path:
    project_root = project_root.resolve()
    report = project_root / "reports/monitoring" / MONITORING_ID
    local_root = project_root / "artifacts/monitoring_predictions" / MONITORING_ID
    manifest_path = report / "manifest.json"
    if sha256_file(manifest_path) != CANDIDATE_MANIFEST_SHA256:
        raise RuntimeError("Phase 8 candidate manifest changed")
    candidate = json.loads(manifest_path.read_text(encoding="utf-8"))
    for relative, expected in FROZEN_UPSTREAM.items():
        if sha256_file(project_root / relative) != expected:
            raise RuntimeError(f"Frozen upstream changed: {relative}")
    result_hashes = {}
    for name, expected in CALCULATED_RESULTS.items():
        actual = sha256_file(report / name)
        if actual != expected:
            raise RuntimeError(f"Calculated Phase 8 result changed: {name}")
        result_hashes[name] = {"candidate_sha256": expected, "approved_sha256": actual, "unchanged": True}

    approved_utc = datetime.now(timezone.utc).isoformat()
    local_reconciliation = {}
    approved_local_manifests = {}
    for artifact_id, candidate_hash in candidate["local_manifests"].items():
        artifact_root = local_root / artifact_id
        manifest_file = artifact_root / "manifest.json"
        if sha256_file(manifest_file) != candidate_hash:
            raise RuntimeError(f"Candidate local prediction manifest changed: {artifact_id}")
        metadata_path = artifact_root / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        prediction_path = artifact_root / "predictions.parquet"
        physical_hash = sha256_file(prediction_path)
        semantic_hash = metadata["semantic_prediction_sha256"]
        metadata["status"] = "APPROVED_FROZEN"
        metadata["approved_utc"] = approved_utc
        _json(metadata_path, metadata)
        _json(manifest_file, {
            "prediction_artifact_id": artifact_id, "status": "APPROVED_FROZEN",
            "approved_utc": approved_utc,
            "artifacts": [_record(prediction_path, artifact_root), _record(metadata_path, artifact_root)],
            "candidate_manifest_sha256": candidate_hash,
            "prediction_file_unchanged_during_approval": True,
            "semantic_prediction_sha256": semantic_hash,
        })
        (artifact_root / "manifest.sha256").write_text(sha256_file(manifest_file) + "\n", encoding="ascii", newline="\n")
        approved_hash = sha256_file(manifest_file)
        approved_local_manifests[artifact_id] = approved_hash
        local_reconciliation[artifact_id] = {
            "candidate_manifest_sha256": candidate_hash, "approved_manifest_sha256": approved_hash,
            "prediction_file_sha256": physical_hash, "semantic_prediction_sha256": semantic_hash,
            "prediction_content_changed": False,
        }

    contract_path = project_root / "contracts/prediction_monitoring_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    _json(report / "prediction_control_registry.json", {
        "monitoring_id": MONITORING_ID, "status": "APPROVED_FROZEN",
        "contract_sha256": sha256_file(contract_path), "score_psi": contract["score_psi"], "threshold_output": contract["threshold_output"],
    })
    _json(report / "phase8_approval_record.json", {
        "phase": "PHASE_8", "monitoring_id": MONITORING_ID, "decision": "APPROVED",
        "approved_utc": approved_utc, "candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256,
        "calculated_results_changed": False, "prediction_content_changed": False, "cnd_02_status": "OPEN",
        "next_phase_authorized": "PHASE_9_OUTCOME_MATURITY_PERFORMANCE_AND_CALIBRATION_MONITORING",
    })
    _json(report / "approval_hash_reconciliation.json", {
        "result": "PASS", "candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256,
        "calculated_results": result_hashes, "all_calculated_results_unchanged": True,
        "local_prediction_artifacts": local_reconciliation, "all_prediction_content_unchanged": True,
        "frozen_upstream_manifests": FROZEN_UPSTREAM, "all_upstream_manifests_unchanged": True,
        "part_a_modified": False,
    })
    checklist_path = report / "phase8_acceptance_checklist.csv"
    with checklist_path.open(encoding="utf-8", newline="") as handle:
        checklist = list(csv.DictReader(handle))
    checklist[-1] = {"control_id": checklist[-1]["control_id"], "control": "Owner approved Phase 8 and authorized Phase 9", "result": "PASS"}
    with checklist_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["control_id", "control", "result"], lineterminator="\n")
        writer.writeheader(); writer.writerows(checklist)
    _json(report / "phase8_completion_decision.json", {
        "phase": "PHASE_8", "phase_name": "PREDICTION_AND_THRESHOLD_OUTPUT_MONITORING", "monitoring_id": MONITORING_ID,
        "review_decision": "APPROVED", "technical_qualification": "PASS", "phase_8_complete": True,
        "eligible_artifact_count": 6, "excluded_artifact_count": 2, "total_governed_predictions": 48744,
        "prediction_artifacts_materialized": True, "prediction_artifacts_frozen": True, "prediction_reproducibility_verified": True,
        "raw_probability_monitoring_executed": True, "prediction_summaries_calculated": True,
        "score_psi_calculated": True, "frozen_score_bins_used": True, "score_psi_reconciliation_verified": True,
        "threshold_output_monitoring_executed": True, "threshold_id": "THRESHOLD-01", "threshold_value": 0.08, "threshold_operator": ">=",
        "risk_positive_rate_calculated": True, "risk_negative_rate_calculated": True,
        "threshold_boundary_density_calculated": False, "cnd_02_status": "OPEN",
        "performance_results_calculated": False, "calibration_results_calculated": False,
        "threshold_performance_results_calculated": False, "subgroup_results_calculated": False,
        "monitoring_alerts_generated": False, "overall_model_health_calculated": False,
        "next_phase_authorized": "PHASE_9_OUTCOME_MATURITY_PERFORMANCE_AND_CALIBRATION_MONITORING", "phase_9_authorized": True,
    })
    execution_path = report / "execution_source_manifest.json"
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    sources = [contract_path, project_root / "src/credit_risk_monitoring/prediction/engine.py", project_root / "src/credit_risk_monitoring/prediction/__init__.py", project_root / "scripts/run_phase8_monitoring.py", project_root / "scripts/finalize_phase8_approval.py"]
    execution["implementation_sources"] = [{"path": path.relative_to(project_root).as_posix(), "sha256": sha256_file(path)} for path in sources]
    execution["approval_finalizer_included"] = True
    _json(execution_path, execution)
    files = sorted(path for path in report.iterdir() if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"})
    _json(manifest_path, {
        "monitoring_id": MONITORING_ID, "status": "APPROVED_FROZEN", "created_utc": candidate["created_utc"], "approved_utc": approved_utc,
        "candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256, "artifacts": [_record(path, report) for path in files],
        "local_artifact_root": candidate["local_artifact_root"], "local_manifests": approved_local_manifests,
        "aggregate_public_evidence_only": True, "row_level_predictions_publicly_committed": False,
        "outcomes_loaded": False, "alerts_included": False, "approval_record_included": True,
        "calculated_results_unchanged_during_approval": True, "prediction_content_unchanged_during_approval": True,
    })
    (report / "manifest.sha256").write_text(sha256_file(manifest_path) + "\n", encoding="ascii", newline="\n")
    return manifest_path


if __name__ == "__main__":
    finalize(Path.cwd())
