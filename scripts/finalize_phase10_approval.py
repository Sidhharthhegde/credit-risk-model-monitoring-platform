"""Record owner approval and freeze the Phase 10 segment evidence package."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from credit_risk_monitoring.qualification.binding import sha256_file


MONITORING_ID = "SEGMENT-MONITORING-01"
CANDIDATE_MANIFEST_SHA256 = "db5e400932538e82aaaa1013f4209d49abbaf74633515417bf19e68926cfb963"
PROSPECTIVE_CONTRACT_SHA256 = "b524d351f4e01e7a67f356dc782a9e297f51a14c44703366e63edf9d43d305a4"
CALCULATED_EVIDENCE = {
    "cross_phase_reconciliation.json": "6aa3cf78628ef17b5c99abdc8bf171386a421514a0155f824b67a0f09141e046",
    "insufficient_evidence_summary.csv": "f5eaf812a22f8592013e64b8ba336b5a675969fe6a3a426e3715ef28fb5860ae",
    "reproducibility_qualification.json": "cff0a0dca606a70f61cc9fc453635081046c275d0f214739994312fca6c7d017",
    "scope_protection_attestation.json": "c2a111ec5355612519ecf6c5ba35ced1f0e7b1baed60d09363354e5910d029ec",
    "segment_assignment_reconciliation.json": "ad2100dd5f64d2d48b6ecec1a0bf8ac04a307ef615888219c990eca617ff08b1",
    "segment_calibration_results.parquet": "cd2e76d038b12e70f9224ee16ff117a40335b06feda05c1ffe7bb6c9bca3059d",
    "segment_definition_registry.json": "90651ed1a7466acfbc63c5350567d04a0f8df0cf88c72dc50c2f0b684f80a883",
    "segment_monitoring_contract_snapshot.json": "910308c730f7feac637d757e077269e8422d7f95eb453b9220a4607bb5e8efce",
    "segment_monitoring_summary.csv": "b32b9f641fde08a7857b8103f8297b3883fe7ac5a1c30988577513c2e29bde21",
    "segment_outcome_eligibility.parquet": "2a6331753f6f60921423f69c4a108fdfde2b1ba09f919906bef40ab17eee9373",
    "segment_performance_results.parquet": "3e7aad312f5c69a2d2b5e84d28ddd1df32efef23c1be873a614be678bda7638a",
    "segment_population_results.parquet": "3a503df25178d7224c46929f7cc6322cebcfa017ef2f44ea84d40255a6e456c3",
    "segment_prediction_results.parquet": "60073f3a7e8786bbbcfd4b38bcd890846edf3efa45ce188ff13f269c5335a290",
    "segment_reference_materialization.json": "c6875c3f1511febbe47f01aaa3dcadc4a70e5d7202a717c8d5eea35bdbea475a",
    "segment_score_psi_results.parquet": "af5c2e666c3cdb60bd1d02f81f624548c895790daa47103e0640bf94c2d6b6e7",
    "segment_threshold_results.parquet": "191931d7cd53d1cfcbca1a68f06c638dc83d1baeb16e223c42988284a525fb9a",
    "synthetic_evidence_attestation.json": "977c358ba21cc18904011c212bd0d2561a2fb918a200d709a8d3e0378ae01ff0",
}
FROZEN_PHASE_MANIFESTS = {
    "reports/protocol/MONITORING-PROTOCOL-01/protocol_manifest.json": "bd0f2a853217c3b4bae3b02f8556eadcfd4e2241a02b76f10064c585157cec70",
    "reports/qualification/RUNTIME-QUALIFICATION-01/qualification_manifest.json": "5bd8b767b67dc176c930a68187047fae449118189a6598fe78a58cbd35d43ba8",
    "reports/reference/REFERENCE-STRATEGY-01/reference_strategy_manifest.json": "e58c2587d8043a2f93522452452e90966f4135bb60ff5bb80b0d6d592c2a6882",
    "reports/adapter/FEATURE-ADAPTER-QUALIFICATION-01/qualification_manifest.json": "21e7279d4b746abcce1b9e6d8930a623eb35140d2b4f9ccfbe977c4914028c5a",
    "reports/reference/REFERENCE-MATERIALIZATION-01/manifest.json": "8fbf4490d78d8c36e89af618cc0bbece4b539feae5321889647037b4b7de2ddc",
    "reports/simulation/SIMULATION-SCENARIO-SET-01/manifest.json": "0681cf14053b82cc7e9da87ce7ca4a227d575a52821de3ab040be9ee445184a5",
    "reports/monitoring/DATA-QUALITY-CONTROL-01/manifest.json": "106033382085f39d838c28eb93cfcf3daab1a1e9c8a3b8217645c60adcec500b",
    "reports/monitoring/FEATURE-DRIFT-MONITORING-01/manifest.json": "64a706d84465e0398391f9d217702343b31aa4d446864a9eca70db89bc930f17",
    "reports/monitoring/PREDICTION-MONITORING-01/manifest.json": "7bb910835b9b7f2df9ac612a72323d37d6395eadd907249d8a8ebd7372bb21d8",
    "reports/monitoring/OUTCOME-PERFORMANCE-MONITORING-01/manifest.json": "17209d875644bfa495889fad0133a9585c5d312aa1164f4a145d4a353139bb5e",
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
        raise RuntimeError("Phase 10 candidate manifest changed")
    candidate = json.loads(manifest_path.read_text(encoding="utf-8"))
    contract_path = project_root / "contracts/segment_monitoring_contract.json"
    if sha256_file(contract_path) != PROSPECTIVE_CONTRACT_SHA256:
        raise RuntimeError("Frozen prospective Phase 10 contract changed")

    evidence_reconciliation = {}
    for name, expected in CALCULATED_EVIDENCE.items():
        actual = sha256_file(report / name)
        if actual != expected:
            raise RuntimeError(f"Calculated Phase 10 evidence changed: {name}")
        evidence_reconciliation[name] = {
            "candidate_sha256": expected, "approved_sha256": actual, "unchanged": True,
        }
    for relative, expected in FROZEN_PHASE_MANIFESTS.items():
        if sha256_file(project_root / relative) != expected:
            raise RuntimeError(f"Frozen Phase 0-9 manifest changed: {relative}")

    approved_utc = datetime.now(timezone.utc).isoformat()
    _json(report / "phase10_approval_record.json", {
        "phase": "PHASE_10", "monitoring_id": MONITORING_ID, "decision": "APPROVED",
        "approved_utc": approved_utc, "candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256,
        "prospective_contract_sha256": PROSPECTIVE_CONTRACT_SHA256,
        "prospective_contract_changed_during_approval": False,
        "calculated_evidence_changed": False, "frozen_phase_0_through_9_manifests_changed": False,
        "cnd_02_status": "OPEN",
        "next_phase_authorized": "PHASE_11_ALERT_ENGINE_BREACH_AGGREGATION_AND_MODEL_HEALTH",
    })
    _json(report / "approval_hash_reconciliation.json", {
        "result": "PASS", "candidate_manifest_sha256": CANDIDATE_MANIFEST_SHA256,
        "prospective_contract_sha256": PROSPECTIVE_CONTRACT_SHA256,
        "calculated_evidence": evidence_reconciliation, "all_calculated_evidence_unchanged": True,
        "frozen_phase_manifests": FROZEN_PHASE_MANIFESTS, "all_frozen_phase_manifests_unchanged": True,
        "label_free_result_row_count": 192, "m06_outcome_result_row_count": 32,
        "phase8_reconciliation_failures": 0, "phase9_threshold_reconciliation_failures": 0,
        "part_a_modified": False,
    })

    checklist_path = report / "phase10_acceptance_checklist.csv"
    with checklist_path.open(encoding="utf-8", newline="") as handle:
        checklist = list(csv.DictReader(handle))
    checklist[-1] = {
        "control_id": checklist[-1]["control_id"],
        "control": "Owner approved Phase 10 and authorized Phase 11 alert engine and model-health design",
        "result": "PASS",
    }
    checklist.append({
        "control_id": "P10-026",
        "control": "Prospective contract and all calculated evidence remained unchanged during approval",
        "result": "PASS",
    })
    with checklist_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["control_id", "control", "result"], lineterminator="\n")
        writer.writeheader(); writer.writerows(checklist)

    decision_path = report / "phase10_completion_decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    for old_key in [
        "m06_discrimination_eligible_segment_count", "m06_discrimination_insufficient_segment_count",
        "m06_threshold_eligible_segment_count", "m06_threshold_insufficient_segment_count",
    ]:
        decision.pop(old_key, None)
    decision.update({
        "review_decision": "APPROVED", "phase_10_complete": True,
        "new_segments_created": False, "post_result_segment_consolidation": False,
        "m06_discrimination_eligible_segments": 21, "m06_discrimination_insufficient_segments": 11,
        "m06_threshold_eligible_segments": 26, "m06_threshold_insufficient_segments": 6,
        "phase_11_authorized": True,
        "next_phase_authorized": "PHASE_11_ALERT_ENGINE_BREACH_AGGREGATION_AND_MODEL_HEALTH",
    })
    _json(decision_path, decision)

    execution_path = report / "execution_source_manifest.json"
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    sources = [
        contract_path, project_root / "src/credit_risk_monitoring/segment/engine.py",
        project_root / "src/credit_risk_monitoring/segment/__init__.py",
        project_root / "scripts/run_phase10_monitoring.py", project_root / "scripts/finalize_phase10_approval.py",
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
        "prospective_contract_sha256": PROSPECTIVE_CONTRACT_SHA256,
        "artifacts": [_record(path, report) for path in files],
        "aggregate_public_evidence_only": True, "row_level_segment_membership_included": False,
        "alerts_included": False, "overall_model_health_included": False, "approval_record_included": True,
        "calculated_evidence_unchanged_during_approval": True,
        "prospective_contract_unchanged_during_approval": True,
    })
    (report / "manifest.sha256").write_text(sha256_file(manifest_path) + "\n", encoding="ascii", newline="\n")
    return manifest_path


if __name__ == "__main__":
    finalize(Path.cwd())
