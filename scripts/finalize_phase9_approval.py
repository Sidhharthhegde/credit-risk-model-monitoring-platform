"""Apply the approved Phase 9 taxonomy remediation and freeze its evidence."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from credit_risk_monitoring.qualification.binding import sha256_file


MONITORING_ID = "OUTCOME-PERFORMANCE-MONITORING-01"
CANDIDATE_MANIFEST_SHA256 = "b9de6fd4e8107ee74525f621d4c3d6148d634dda59fa4782168ac1c99fa93643"
CALCULATED_RESULTS = {
    "performance_results.parquet": "208367e3fd65807d12c029f9219e1ad257a23d2830b5e73c48e64dc4c8eeb164",
    "calibration_results.parquet": "85c84937bb16269af4a61277f47c03cd5e2459aa3b96fc036fe88b246df7c20b",
    "calibration_band_results.parquet": "559edc0cb075e61169f70a228a23558ce005fdfc87011f20c733b6971e909897",
    "threshold_performance_results.parquet": "a4bf28b36185f556093b2c10488b54d80e6a57b95778d8eef87a10b916795bfc",
}
FROZEN_INPUTS = {
    "artifacts/monitoring_predictions/PREDICTION-MONITORING-01/SIM-M06-PREDICTIONS-01/predictions.parquet": "b73ce6d333d562dfe9bc4c5ccc8f08705f0aa11c83acc6786dd6f226b71b3f3e",
    "artifacts/monitoring_predictions/PREDICTION-MONITORING-01/SIM-M06-PREDICTIONS-01/manifest.json": "1d01327698856838404610abcbfacccbeb705bd883d7f56786773056dd526fcb",
    "artifacts/simulation_scenarios/SIMULATION-SCENARIO-SET-01/outcomes/SIM-M06-SYNTHETIC-OUTCOMES-01/data.parquet": "24bdc41b9a14e11e779c9c2724ca4aae156c0a0f1b182d3f29e106d4048b9816",
    "artifacts/simulation_scenarios/SIMULATION-SCENARIO-SET-01/outcomes/SIM-M06-SYNTHETIC-OUTCOMES-01/manifest.json": "03855cf310b1308f38c72b08082f5d347f92fe556570d0e996f41025d44c2abc",
    "reports/monitoring/PREDICTION-MONITORING-01/manifest.json": "7bb910835b9b7f2df9ac612a72323d37d6395eadd907249d8a8ebd7372bb21d8",
    "reports/reference/REFERENCE-MATERIALIZATION-01/manifest.json": "8fbf4490d78d8c36e89af618cc0bbece4b539feae5321889647037b4b7de2ddc",
    "reports/simulation/SIMULATION-SCENARIO-SET-01/manifest.json": "0681cf14053b82cc7e9da87ce7ca4a227d575a52821de3ab040be9ee445184a5",
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
        raise RuntimeError("Phase 9 candidate manifest changed")
    candidate = json.loads(manifest_path.read_text(encoding="utf-8"))

    calculated_reconciliation = {}
    for name, expected in CALCULATED_RESULTS.items():
        actual = sha256_file(report / name)
        if actual != expected:
            raise RuntimeError(f"Calculated Phase 9 artifact changed: {name}")
        calculated_reconciliation[name] = {
            "candidate_sha256": expected, "approved_sha256": actual, "unchanged": True,
        }
    for relative, expected in FROZEN_INPUTS.items():
        if sha256_file(project_root / relative) != expected:
            raise RuntimeError(f"Frozen Phase 9 input changed: {relative}")

    contract_path = project_root / "contracts/outcome_performance_monitoring_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract["gate_vocabulary"]["evidence_status"] != ["ELIGIBLE", "NOT_ASSESSABLE"]:
        raise RuntimeError("Generic evidence-eligibility vocabulary was not applied")
    _json(report / "outcome_monitoring_contract_snapshot.json", contract)

    eligibility_path = report / "evidence_eligibility_results.json"
    eligibility = json.loads(eligibility_path.read_text(encoding="utf-8"))
    for row in eligibility["results"]:
        available = row["scenario_id"] == "SIM-M06"
        row["evidence_status"] = "ELIGIBLE" if available else "NOT_ASSESSABLE"
        row.pop("reason", None)
        row["eligibility_basis"] = "OUTCOME_AVAILABLE_MATURED_AND_RECONCILED" if available else None
        row["non_assessability_reason"] = None if available else "OUTCOME_NOT_AVAILABLE"
    _json(eligibility_path, eligibility)

    summary_path = report / "scenario_outcome_summary.csv"
    with summary_path.open(encoding="utf-8", newline="") as handle:
        summary = list(csv.DictReader(handle))
    for row in summary:
        if row["scenario_id"] == "SIM-M06":
            row["evidence_status"] = "ELIGIBLE"
    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(summary)

    approved_utc = datetime.now(timezone.utc).isoformat()
    _json(report / "phase9_approval_record.json", {
        "phase": "PHASE_9", "monitoring_id": MONITORING_ID, "decision": "APPROVED",
        "approved_utc": approved_utc, "candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256,
        "conditional_taxonomy_issue_resolved": True, "calculated_results_changed": False,
        "frozen_prediction_or_outcome_content_changed": False, "cnd_02_status": "OPEN",
        "next_phase_authorized": "PHASE_10_SEGMENT_AND_SUBPOPULATION_MONITORING",
    })
    _json(report / "approval_hash_reconciliation.json", {
        "result": "PASS", "candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256,
        "calculated_results": calculated_reconciliation, "all_calculated_results_unchanged": True,
        "frozen_inputs": FROZEN_INPUTS, "all_frozen_inputs_unchanged": True,
        "taxonomy_remediation_only": True, "part_a_modified": False,
    })

    checklist_path = report / "phase9_acceptance_checklist.csv"
    with checklist_path.open(encoding="utf-8", newline="") as handle:
        checklist = list(csv.DictReader(handle))
    checklist.append({
        "control_id": "P9-024",
        "control": "Evidence eligibility is generic and synthetic evidence type remains independent",
        "result": "PASS",
    })
    checklist[-2] = {
        "control_id": checklist[-2]["control_id"],
        "control": "Owner approved Phase 9 and authorized Phase 10 segment and subpopulation monitoring",
        "result": "PASS",
    }
    with checklist_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["control_id", "control", "result"], lineterminator="\n")
        writer.writeheader(); writer.writerows(checklist)

    decision_path = report / "phase9_completion_decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision.update({
        "phase_name": "OUTCOME_MATURITY_PERFORMANCE_AND_CALIBRATION_MONITORING",
        "review_decision": "APPROVED", "phase_9_complete": True,
        "m06_outcome_availability": "AVAILABLE", "m06_maturity_status": "MATURED",
        "m06_evidence_status": "ELIGIBLE", "phase_10_authorized": True,
        "next_phase_authorized": "PHASE_10_SEGMENT_AND_SUBPOPULATION_MONITORING",
    })
    _json(decision_path, decision)

    execution_path = report / "execution_source_manifest.json"
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    sources = [
        contract_path, project_root / "src/credit_risk_monitoring/outcome/engine.py",
        project_root / "src/credit_risk_monitoring/outcome/__init__.py",
        project_root / "scripts/run_phase9_monitoring.py", project_root / "scripts/finalize_phase9_approval.py",
    ]
    execution["implementation_sources"] = [
        {"path": path.relative_to(project_root).as_posix(), "sha256": sha256_file(path)} for path in sources
    ]
    execution["approval_finalizer_included"] = True
    _json(execution_path, execution)

    files = sorted(path for path in report.iterdir() if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"})
    _json(manifest_path, {
        "monitoring_id": MONITORING_ID, "status": "APPROVED_FROZEN",
        "created_utc": candidate["created_utc"], "approved_utc": approved_utc,
        "candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256,
        "artifacts": [_record(path, report) for path in files],
        "aggregate_public_evidence_only": True, "row_level_joined_evidence_included": False,
        "synthetic_evidence_only": True, "alerts_included": False, "approval_record_included": True,
        "calculated_results_unchanged_during_approval": True,
        "prediction_and_outcome_content_unchanged_during_approval": True,
        "taxonomy_remediation_only": True,
    })
    (report / "manifest.sha256").write_text(sha256_file(manifest_path) + "\n", encoding="ascii", newline="\n")
    return manifest_path


if __name__ == "__main__":
    finalize(Path.cwd())
