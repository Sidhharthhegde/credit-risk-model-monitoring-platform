"""Resolve the conditional Phase 5 review and freeze metadata without changing row data."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PRE_REMEDIATION_MANIFEST = "31af9c926db47b1bc5c08fa29b37b582ac832781427cad00c7f1845261442e5e"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def record(path: Path, root: Path) -> dict[str, Any]:
    return {"path": path.relative_to(root).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256(path)}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    report = root / "reports/simulation/SIMULATION-SCENARIO-SET-01"
    local = root / "artifacts/simulation_scenarios/SIMULATION-SCENARIO-SET-01"
    contract_path = root / "contracts/simulation_scenario_contract.json"
    if sha256(report / "manifest.json") != PRE_REMEDIATION_MANIFEST:
        raise RuntimeError("Phase 5 candidate manifest does not match the conditional review input")
    if (report / "phase5_approval_record.json").exists():
        raise FileExistsError("Phase 5 approval already applied")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract["status"] != "APPROVED_FROZEN":
        raise RuntimeError("Corrected scenario contract has not been approved")
    approved_utc = datetime.now(timezone.utc).isoformat()

    before = {}
    for metadata_path in sorted(local.rglob("metadata.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        data_path = metadata_path.parent / "data.parquet"
        before[metadata["artifact_id"]] = {
            "data_sha256": sha256(data_path),
            "content_sha256": metadata["content_sha256"],
        }
        if before[metadata["artifact_id"]]["data_sha256"] != metadata["data_sha256"]:
            raise RuntimeError(f"Pre-remediation data hash mismatch: {metadata['artifact_id']}")

    for metadata_path in sorted(local.rglob("metadata.json")):
        artifact_root = metadata_path.parent
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["status"] = "APPROVED_FROZEN"
        if metadata["artifact_id"] == "SIM-M05-SOURCE-LOSS-DIAGNOSTIC-01":
            metadata.pop("source_state", None)
            metadata["availability_state"] = "SOURCE_DEGRADED"
            metadata["governance_state"] = "SOURCE_POLICY_REQUIRED"
            metadata["fallback_status"] = "NO_APPROVED_FALLBACK"
            metadata["cnd_02_status"] = "OPEN"
            metadata["technical_scoring"] = "PASS"
            metadata["authoritative_use_permitted"] = False
        write_json(metadata_path, metadata)
        manifest_path = artifact_root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "APPROVED_FROZEN"
        manifest["artifacts"] = [record(artifact_root / name, artifact_root) for name in ("data.parquet", "metadata.json")]
        write_json(manifest_path, manifest)
        (artifact_root / "manifest.sha256").write_text(sha256(manifest_path) + "\n", encoding="ascii", newline="\n")

    after = {}
    for metadata_path in sorted(local.rglob("metadata.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        after[metadata["artifact_id"]] = {
            "data_sha256": sha256(metadata_path.parent / "data.parquet"),
            "content_sha256": metadata["content_sha256"],
        }
    if before != after:
        raise RuntimeError("A row-level artifact changed during taxonomy remediation")

    source_path = report / "source_degradation_scenarios.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source.pop("source_state", None)
    source.update({
        "availability_state": "SOURCE_DEGRADED",
        "governance_state": "SOURCE_POLICY_REQUIRED",
        "fallback_status": "NO_APPROVED_FALLBACK",
        "cnd_02_status": "OPEN",
        "technical_scoring": "PASS",
        "authoritative_completion": False,
    })
    write_json(source_path, source)

    integrity_path = report / "scenario_integrity_qualification.json"
    integrity = json.loads(integrity_path.read_text(encoding="utf-8"))
    for item in [*integrity["base_artifacts"], *integrity["scenario_artifacts"]]:
        item["status"] = "APPROVED_FROZEN"
        if item["artifact_id"] == "SIM-M05-SOURCE-LOSS-DIAGNOSTIC-01":
            item.pop("source_state", None)
            item.update({
                "availability_state": "SOURCE_DEGRADED",
                "governance_state": "SOURCE_POLICY_REQUIRED",
                "fallback_status": "NO_APPROVED_FALLBACK",
                "cnd_02_status": "OPEN",
                "technical_scoring": "PASS",
                "authoritative_use_permitted": False,
            })
    integrity["conditional_review_blocker"] = "RESOLVED"
    integrity["source_state_dimensional_model_conforms_to_phase0"] = True
    integrity["row_level_content_hashes_unchanged_during_remediation"] = True
    write_json(integrity_path, integrity)

    registry_path = report / "scenario_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["status"] = "APPROVED_FROZEN"
    registry["contract_sha256"] = sha256(contract_path)
    registry["scenarios"] = contract["scenarios"]
    write_json(registry_path, registry)
    transformations_path = report / "scenario_transformation_manifest.json"
    transformations = json.loads(transformations_path.read_text(encoding="utf-8"))
    transformations["status"] = "APPROVED_FROZEN"
    write_json(transformations_path, transformations)
    synthetic_path = report / "synthetic_outcome_specification.json"
    synthetic = json.loads(synthetic_path.read_text(encoding="utf-8"))
    synthetic["mechanism"] = next(item for item in contract["scenarios"] if item["scenario_id"] == "SIM-M06")["synthetic_outcomes"]
    synthetic["deterministic_streams_independent"] = True
    write_json(synthetic_path, synthetic)

    source_manifest_path = report / "generation_source_manifest.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    for item in source_manifest["implementation_sources"]:
        item["sha256"] = sha256(root / item["path"])
    source_manifest["conditional_taxonomy_remediation"] = "SOURCE_DEGRADED_PLUS_SEPARATE_GOVERNANCE_AND_FALLBACK_FIELDS"
    write_json(source_manifest_path, source_manifest)

    preservation = {
        "result": "PASS",
        "candidate_manifest_sha256": PRE_REMEDIATION_MANIFEST,
        "all_row_level_data_file_hashes_unchanged": True,
        "all_semantic_content_hashes_unchanged": True,
        "cohort_assignment_unchanged": True,
        "six_pristine_base_hashes_unchanged": True,
        "six_primary_scenario_hashes_unchanged": True,
        "m05_variant_hashes_unchanged": True,
        "m06_synthetic_outcome_hash_unchanged": True,
        "artifact_hashes": after,
    }
    write_json(report / "conditional_remediation_hash_reconciliation.json", preservation)
    write_json(report / "phase5_approval_record.json", {
        "scenario_set_id": "SIMULATION-SCENARIO-SET-01",
        "initial_review_decision": "CONDITIONAL_APPROVAL",
        "blocking_issue": "COMPOSITE_M05_SOURCE_STATE",
        "resolution": "PASS_PHASE0_DIMENSIONAL_SOURCE_STATE_RESTORED",
        "final_review_decision": "APPROVED",
        "approver_role": "USER_PROTOCOL_OWNER",
        "approved_utc": approved_utc,
        "approved_candidate_manifest_sha256": PRE_REMEDIATION_MANIFEST,
        "row_level_scenarios_rebuilt": False,
        "row_level_content_hashes_unchanged": True,
        "monitoring_execution_authorized": False,
        "next_phase_authorized": "PHASE_6_DATA_QUALITY_AND_INPUT_CONTROL_MONITORING",
    })
    checklist_path = report / "phase5_acceptance_checklist.csv"
    checklist = checklist_path.read_text(encoding="utf-8").replace(
        "P5-018,Owner approval and freeze deferred,PASS",
        "P5-018,Conditional blocker resolved and owner approval and freeze recorded,PASS",
    )
    checklist_path.write_text(checklist, encoding="utf-8", newline="\n")
    write_json(report / "phase5_completion_decision.json", {
        "phase": "PHASE_5",
        "phase_name": "SIMULATED_MONITORING_COHORTS_AND_SCENARIO_GENERATION",
        "scenario_set_id": "SIMULATION-SCENARIO-SET-01",
        "technical_qualification": "PASS",
        "review_decision": "APPROVED",
        "phase_5_complete": True,
        "cohort_assignment_frozen": True,
        "pristine_bases_frozen": True,
        "scenario_artifacts_frozen": True,
        "simulation_cohorts_created": True,
        "scenario_reproducibility_verified": True,
        "synthetic_outcome_scenario_created": True,
        "synthetic_evidence_empirical": False,
        "cnd_02_status": "OPEN",
        "monitoring_results_calculated": False,
        "monitoring_alerts_generated": False,
        "monitoring_execution_authorized": False,
        "next_phase_authorized": "PHASE_6_DATA_QUALITY_AND_INPUT_CONTROL_MONITORING",
    })

    files = sorted(path for path in report.iterdir() if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"})
    local_manifests = {path.parent.relative_to(local).as_posix(): sha256(path) for path in local.rglob("manifest.json")}
    manifest = {
        "scenario_set_id": "SIMULATION-SCENARIO-SET-01",
        "status": "APPROVED_FROZEN",
        "approved_utc": approved_utc,
        "pre_remediation_manifest_sha256": PRE_REMEDIATION_MANIFEST,
        "artifacts": [record(path, report) for path in files],
        "local_artifact_root": "artifacts/simulation_scenarios/SIMULATION-SCENARIO-SET-01",
        "local_manifests": local_manifests,
        "monitoring_results_included": False,
        "approval_record_included": True,
    }
    write_json(report / "manifest.json", manifest)
    (report / "manifest.sha256").write_text(sha256(report / "manifest.json") + "\n", encoding="ascii", newline="\n")
    print(sha256(report / "manifest.json"))


if __name__ == "__main__":
    main()
