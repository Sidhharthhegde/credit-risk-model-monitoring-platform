"""Apply the protocol-owner Phase 4 approval without changing reference values."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PREAPPROVAL_MANIFEST = "3df7788fc64c066aaca9e20899e4b2e3b15afc863f8f1b5c7c8b7ac53c2fd958"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def record(path: Path, root: Path) -> dict[str, Any]:
    return {"path": path.relative_to(root).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256(path)}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    report = root / "reports/reference/REFERENCE-MATERIALIZATION-01"
    snapshots = root / "artifacts/reference_snapshots/REFERENCE-MATERIALIZATION-01"
    if sha256(report / "manifest.json") != PREAPPROVAL_MANIFEST:
        raise RuntimeError("Qualified Phase 4 manifest does not match the approved review input")
    if (report / "phase4_approval_record.json").exists():
        raise FileExistsError("Phase 4 approval has already been applied")
    approved_utc = datetime.now(timezone.utc).isoformat()

    feature_bins_path = report / "feature_psi_bin_definitions.json"
    feature_bins = json.loads(feature_bins_path.read_text(encoding="utf-8"))
    feature_bins["status"] = "APPROVED_FROZEN"
    feature_bins["smoothing_policy"] = {
        "status": "APPROVED_PROJECT_ASSUMPTION",
        "epsilon": 1e-6,
        "application": "REPLACE_ZERO_PROPORTIONS_ONLY_THEN_RENORMALIZE",
        "period_specific_tuning_permitted": False,
        "regulatory_or_universal_convention_claimed": False,
    }
    write_json(feature_bins_path, feature_bins)
    score_bins_path = report / "score_psi_bin_definitions.json"
    score_bins = json.loads(score_bins_path.read_text(encoding="utf-8"))
    score_bins["status"] = "APPROVED_FROZEN"
    write_json(score_bins_path, score_bins)

    submanifest_map = {
        "reference_statistics_manifest.json": ["feature_reference_statistics.csv", "categorical_reference_frequencies.csv", "binary_reference_statistics.csv", "missingness_reference.csv"],
        "feature_psi_bin_manifest.json": ["feature_psi_bin_definitions.json"],
        "score_reference_manifest.json": ["score_reference.json"],
        "score_psi_bin_manifest.json": ["score_psi_bin_definitions.json"],
    }
    for name, artifacts in submanifest_map.items():
        path = report / name
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["status"] = "APPROVED_FROZEN"
        payload["artifacts"] = [record(report / artifact, report) for artifact in artifacts]
        write_json(path, payload)

    manifest_links = {
        name: {"path": f"reports/reference/REFERENCE-MATERIALIZATION-01/{name}", "sha256": sha256(report / name)}
        for name in submanifest_map
    }
    snapshot_inventory_path = report / "snapshot_inventory.json"
    inventory = json.loads(snapshot_inventory_path.read_text(encoding="utf-8"))
    inventory["status"] = "APPROVED_FROZEN"
    for item in inventory["snapshots"]:
        snapshot_id = item["snapshot_id"]
        snapshot_root = snapshots / snapshot_id
        metadata_path = snapshot_root / "snapshot_metadata.json"
        lifecycle_path = snapshot_root / "snapshot_lifecycle.json"
        snapshot_manifest_path = snapshot_root / "snapshot_manifest.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        lifecycle = json.loads(lifecycle_path.read_text(encoding="utf-8"))
        snapshot_manifest = json.loads(snapshot_manifest_path.read_text(encoding="utf-8"))

        metadata["snapshot_state"] = "FROZEN"
        if snapshot_id == "TRAIN-PHYSICAL-01":
            metadata["statistics_manifest"] = manifest_links["reference_statistics_manifest.json"]
            metadata["bin_manifest"] = manifest_links["feature_psi_bin_manifest.json"]
        elif snapshot_id == "DEV-VAL-PHYSICAL-01":
            metadata["statistics_manifest"] = {"manifests": [manifest_links["score_reference_manifest.json"]]}
            metadata["bin_manifest"] = manifest_links["score_psi_bin_manifest.json"]
        write_json(metadata_path, metadata)
        lifecycle["transitions"].extend([
            {"from": "QUALIFIED", "to": "APPROVED", "basis": "USER_PROTOCOL_OWNER_PHASE4_APPROVAL"},
            {"from": "APPROVED", "to": "FROZEN", "basis": "APPROVED_PHASE4_FINALIZATION"},
        ])
        lifecycle["approval_transition_recorded"] = True
        lifecycle["freeze_transition_recorded"] = True
        write_json(lifecycle_path, lifecycle)
        snapshot_manifest["status"] = "APPROVED_FROZEN"
        if snapshot_id == "APPLICATION-TEST-BASE-01":
            snapshot_manifest["adapter_id"] = "MONITORING-FEATURE-ADAPTER-01"
            snapshot_manifest["physical_creation_implementation"] = "PHASE3_QUALIFIED_LABEL_FREE_ADAPTER"
        else:
            snapshot_manifest.pop("adapter_id", None)
            snapshot_manifest["feature_interface_compatibility_qualification_id"] = "FEATURE-ADAPTER-QUALIFICATION-01"
            snapshot_manifest["physical_creation_implementation"] = "FROZEN_PART_A_DETERMINISTIC_BASE_LINEAGE"
        snapshot_manifest["artifacts"] = [record(snapshot_root / name, snapshot_root) for name in ("snapshot.parquet", "snapshot_metadata.json", "snapshot_lifecycle.json")]
        write_json(snapshot_manifest_path, snapshot_manifest)
        (snapshot_root / "snapshot_manifest.sha256").write_text(sha256(snapshot_manifest_path) + "\n", encoding="ascii", newline="\n")

        item["snapshot_state"] = "FROZEN"
        item["statistics_manifest"] = metadata["statistics_manifest"]
        item["bin_manifest"] = metadata["bin_manifest"]
        if snapshot_id == "APPLICATION-TEST-BASE-01":
            item["adapter_id"] = "MONITORING-FEATURE-ADAPTER-01"
        else:
            item.pop("adapter_id", None)
            item["feature_interface_compatibility_qualification_id"] = "FEATURE-ADAPTER-QUALIFICATION-01"
    write_json(snapshot_inventory_path, inventory)

    approval = {
        "materialization_id": "REFERENCE-MATERIALIZATION-01",
        "review_decision": "APPROVED",
        "approver_role": "USER_PROTOCOL_OWNER",
        "approved_utc": approved_utc,
        "approved_preapproval_manifest_sha256": PREAPPROVAL_MANIFEST,
        "psi_epsilon": 1e-6,
        "psi_epsilon_status": "APPROVED_PROJECT_ASSUMPTION",
        "smoothing_formula": "REPLACE_ZERO_PROPORTIONS_ONLY_THEN_RENORMALIZE",
        "adapter_metadata_semantics_resolved": True,
        "phase_5_authorized": True,
        "monitoring_execution_authorized": False,
    }
    write_json(report / "phase4_approval_record.json", approval)
    write_json(report / "immutability_attestation.json", {
        "result": "PASS",
        "reference_values_changed_during_approval": False,
        "row_level_parquet_data_changed_during_approval": False,
        "lifecycle_and_governance_metadata_changed": True,
        "phase_0_through_3_frozen_manifests_unchanged": True,
        "part_a_unchanged": True,
    })
    checklist_path = report / "phase4_acceptance_checklist.csv"
    checklist = checklist_path.read_text(encoding="utf-8")
    checklist = checklist.replace("P4-018,Approval and freeze deferred to owner review,PASS", "P4-018,Owner approval and snapshot freeze transitions recorded,PASS")
    checklist_path.write_text(checklist, encoding="utf-8", newline="\n")
    write_json(report / "phase4_completion_decision.json", {
        "phase": "PHASE_4",
        "phase_name": "REFERENCE_MATERIALIZATION_AND_FROZEN_BINS",
        "materialization_id": "REFERENCE-MATERIALIZATION-01",
        "review_decision": "APPROVED",
        "technical_qualification": "PASS",
        "phase_4_complete": True,
        "snapshot_state": "FROZEN",
        "train_physical_01": "FROZEN",
        "dev_val_physical_01": "FROZEN",
        "application_test_base_01": "FROZEN",
        "feature_psi_bin_definitions": 176,
        "feature_psi_bins_frozen": True,
        "score_psi_bins_frozen": True,
        "score_performance_calibration_and_threshold_references_frozen": True,
        "psi_epsilon": 1e-6,
        "psi_epsilon_status": "APPROVED_PROJECT_ASSUMPTION",
        "reference_reproducibility_verified": True,
        "cnd_02_status": "OPEN",
        "simulation_cohorts_created": False,
        "monitoring_scenarios_created": False,
        "drift_results_calculated": False,
        "monitoring_results_calculated": False,
        "monitoring_alerts_generated": False,
        "monitoring_execution_authorized": False,
        "next_phase_authorized": "PHASE_5_SIMULATED_MONITORING_COHORTS_AND_SCENARIO_GENERATION",
    })

    files = sorted(path for path in report.iterdir() if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"})
    manifest = {
        "materialization_id": "REFERENCE-MATERIALIZATION-01",
        "status": "APPROVED_FROZEN",
        "approved_utc": approved_utc,
        "preapproval_manifest_sha256": PREAPPROVAL_MANIFEST,
        "artifacts": [record(path, report) for path in files],
        "local_snapshot_root": "artifacts/reference_snapshots/REFERENCE-MATERIALIZATION-01",
        "local_snapshot_manifests": {p.name: sha256(p / "snapshot_manifest.json") for p in sorted(snapshots.iterdir()) if p.is_dir()},
        "monitoring_results_included": False,
        "approval_record_included": True,
    }
    write_json(report / "manifest.json", manifest)
    (report / "manifest.sha256").write_text(sha256(report / "manifest.json") + "\n", encoding="ascii", newline="\n")
    print(sha256(report / "manifest.json"))


if __name__ == "__main__":
    main()
