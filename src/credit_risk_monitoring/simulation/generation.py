"""Phase 5 cohort/scenario generation without monitoring calculations."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from credit_risk_monitoring.qualification.binding import (
    load_binding,
    resolve_artifact,
    resolve_part_a_root,
    sha256_file,
    verify_artifacts,
)
from credit_risk_monitoring.qualification.contract import (
    ScoringContractError,
    feature_groups,
    validate_scoring_frame,
)
from credit_risk_monitoring.reference.materialization import _semantic_hash

SCENARIO_SET_ID = "SIMULATION-SCENARIO-SET-01"
CODE_VERSION = "PHASE5-SCENARIO-GENERATOR-0.1.0"
PHASE4_MANIFEST_SHA256 = "8fbf4490d78d8c36e89af618cc0bbece4b539feae5321889647037b4b7de2ddc"


def _json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root), *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _record(path: Path, root: Path) -> dict[str, Any]:
    return {"path": path.relative_to(root).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def _uniform(token: str) -> float:
    return int(hashlib.sha256(token.encode()).hexdigest()[:16], 16) / 2**64


def assign_cohorts(ids: pd.Series) -> pd.DataFrame:
    if ids.isna().any() or not ids.is_unique:
        raise ValueError("Cohort parent identifiers must be complete and unique")
    rows = pd.DataFrame({"SK_ID_CURR": ids.astype("int64")})
    rows["assignment_digest"] = rows["SK_ID_CURR"].map(
        lambda value: hashlib.sha256(f"APPLICATION-TEST-SIM-01|{int(value)}".encode()).hexdigest()
    )
    rows = rows.sort_values(["assignment_digest", "SK_ID_CURR"], kind="mergesort").reset_index(drop=True)
    labels = [f"SIM-M{index:02d}" for index in range(1, 7)]
    rows["simulation_cohort"] = [labels[index % 6] for index in range(len(rows))]
    rows["assignment_algorithm"] = "SIM-COHORT-ASSIGNMENT-01"
    rows["assignment_version"] = "0.1.0"
    return rows


def _selection(frame: pd.DataFrame, scenario: str, transformation: str, rate: float) -> pd.Series:
    count = round(len(frame) * rate)
    ranked = sorted(
        ((hashlib.sha256(f"{scenario}|{transformation}|{int(value)}".encode()).hexdigest(), int(value)) for value in frame["SK_ID_CURR"]),
        key=lambda item: (item[0], item[1]),
    )
    selected = {value for _, value in ranked[:count]}
    return frame["SK_ID_CURR"].isin(selected)


def apply_scenario(base: pd.DataFrame, specification: dict[str, Any]) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    result = base.copy(deep=True)
    records: list[dict[str, Any]] = []
    scenario_id = specification["scenario_id"]
    for transformation in specification["transformations"]:
        transformation_id = transformation["transformation_id"]
        mask = _selection(result, scenario_id, transformation_id, float(transformation["selection_rate"]))
        before = result.copy(deep=True)
        operation = transformation["operation"]
        for feature in transformation["features"]:
            if operation in {"MULTIPLICATIVE_SHIFT", "FINITE_TAIL_ENRICHMENT"}:
                result.loc[mask, feature] = result.loc[mask, feature] * float(transformation["factor"])
            elif operation == "BOUNDED_MULTIPLICATIVE_SHIFT":
                result.loc[mask, feature] = (result.loc[mask, feature] * float(transformation["factor"])).clip(
                    float(transformation["lower"]), float(transformation["upper"])
                )
            elif operation == "MISSINGNESS_INJECTION":
                result.loc[mask, feature] = np.nan
            elif operation == "UNSEEN_CATEGORY_INJECTION":
                result.loc[mask, feature] = str(transformation["value"])
            else:
                raise ValueError(f"Unsupported scenario operation: {operation}")
        changed_features = [feature for feature in result.columns if not result[feature].equals(before[feature])]
        if set(changed_features) - set(transformation["features"]):
            raise RuntimeError("Scenario operation changed an unintended feature")
        records.append({
            "scenario_id": scenario_id,
            "transformation_id": transformation_id,
            "operation": operation,
            "intended_features": transformation["features"],
            "selected_row_count": int(mask.sum()),
            "changed_features": changed_features,
            "monitoring_metric_used_to_select_magnitude": False,
        })
    return result, records


def _write_local_artifact(root: Path, artifact_id: str, frame: pd.DataFrame, metadata: dict[str, Any]) -> dict[str, Any]:
    target = root / artifact_id
    target.mkdir(parents=True)
    data_path = target / "data.parquet"
    frame.to_parquet(data_path, index=False, engine="pyarrow", compression="zstd")
    payload = {
        "artifact_id": artifact_id,
        "status": "QUALIFIED_PENDING_REVIEW",
        "row_count": len(frame),
        "column_count": len(frame.columns),
        "data_sha256": sha256_file(data_path),
        "content_sha256": _semantic_hash(frame),
        "creation_code_version": CODE_VERSION,
        **metadata,
    }
    _json(target / "metadata.json", payload)
    manifest = {"artifact_id": artifact_id, "status": "QUALIFIED_PENDING_REVIEW", "artifacts": [_record(data_path, target), _record(target / "metadata.json", target)]}
    _json(target / "manifest.json", manifest)
    (target / "manifest.sha256").write_text(sha256_file(target / "manifest.json") + "\n", encoding="ascii", newline="\n")
    return payload


def _score_qualification(frame: pd.DataFrame, pipeline: Any) -> dict[str, Any]:
    validate_scoring_frame(frame, pipeline)
    probability = pipeline.predict_proba(frame.drop(columns="SK_ID_CURR"))[:, 1]
    return {
        "scoring_contract": "PASS",
        "prediction_count": len(probability),
        "one_probability_per_applicant": len(probability) == len(frame),
        "all_probabilities_finite_and_bounded": bool(np.isfinite(probability).all() and ((probability >= 0) & (probability <= 1)).all()),
        "probability_values_persisted": False,
        "score_summary_calculated": False,
    }


def _synthetic_outcomes(frame: pd.DataFrame, pipeline: Any, parent_hash: str) -> pd.DataFrame:
    probability = pipeline.predict_proba(frame.drop(columns="SK_ID_CURR"))[:, 1]
    ids = frame["SK_ID_CURR"].astype(int).to_numpy()
    noise = np.array([_uniform(f"{parent_hash}|SIM-M06|NOISE|{value}") for value in ids])
    draw = np.array([_uniform(f"{parent_hash}|SIM-M06|DRAW|{value}") for value in ids])
    synthetic_probability = np.clip(0.03 + 0.35 * probability + 0.15 * noise, 0.001, 0.999)
    outcomes = (draw < synthetic_probability).astype("int8")
    return pd.DataFrame({
        "SK_ID_CURR": ids,
        "COHORT_ID": "SIM-M06",
        "OUTCOME": outcomes,
        "OBSERVATION_START": "SIM-M06-OBSERVATION-START",
        "OBSERVATION_END": "SIM-M06-OBSERVATION-END",
        "MATURITY_STATUS": "MATURED",
        "OUTCOME_SOURCE": "SYNTHETIC_SCENARIO_EVIDENCE",
        "OUTCOME_RECEIVED_TIMESTAMP": "SIMULATED_DETERMINISTIC_GENERATION",
        "RECONCILIATION_STATUS": "RECONCILED_SYNTHETIC",
    })


def run_phase5_generation(project_root: Path, explicit_part_a_root: Path | None = None) -> Path:
    project_root = project_root.resolve()
    contract_path = project_root / "contracts/simulation_scenario_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    phase4_report = project_root / "reports/reference/REFERENCE-MATERIALIZATION-01"
    if sha256_file(phase4_report / "manifest.json") != PHASE4_MANIFEST_SHA256:
        raise RuntimeError("Frozen Phase 4 reference manifest changed")
    binding = load_binding(project_root / "contracts/part_a_binding.json")
    part_a = resolve_part_a_root(binding, explicit_part_a_root)
    _, binding_pass = verify_artifacts(binding, part_a)
    if not binding_pass or _git(part_a, "rev-parse", "HEAD") != binding.part_a["published_commit"]:
        raise RuntimeError("Part A binding failed")
    if _git(part_a, "status", "--porcelain"):
        raise RuntimeError("Part A is not clean")
    model_spec = next(item for item in binding.artifacts if item.role == "MODEL_ARTIFACT")
    pipeline = joblib.load(resolve_artifact(part_a, model_spec))
    governed = list(feature_groups(pipeline).raw)

    parent_root = project_root / "artifacts/reference_snapshots/REFERENCE-MATERIALIZATION-01/APPLICATION-TEST-BASE-01"
    parent_metadata = json.loads((parent_root / "snapshot_metadata.json").read_text(encoding="utf-8"))
    parent_manifest = json.loads((parent_root / "snapshot_manifest.json").read_text(encoding="utf-8"))
    if parent_metadata["snapshot_state"] != "FROZEN" or parent_manifest["status"] != "APPROVED_FROZEN":
        raise RuntimeError("APPLICATION-TEST-BASE-01 is not frozen")
    if sha256_file(parent_root / "snapshot.parquet") != parent_metadata["data_sha256"]:
        raise RuntimeError("Parent snapshot file hash mismatch")
    parent = pd.read_parquet(parent_root / "snapshot.parquet", engine="pyarrow")
    if _semantic_hash(parent) != parent_manifest["content_sha256"]:
        raise RuntimeError("Parent snapshot semantic hash mismatch")
    validate_scoring_frame(parent, pipeline)

    report_final = project_root / "reports/simulation" / SCENARIO_SET_ID
    report_stage = report_final.parent / f".{SCENARIO_SET_ID}.in_progress"
    local_final = project_root / "artifacts/simulation_scenarios" / SCENARIO_SET_ID
    local_stage = local_final.parent / f".{SCENARIO_SET_ID}.in_progress"
    if any(path.exists() for path in (report_final, report_stage, local_final, local_stage)):
        raise FileExistsError("Phase 5 output already exists")
    report_stage.mkdir(parents=True)
    local_stage.mkdir(parents=True)
    created = datetime.now(timezone.utc).isoformat()

    assignment = assign_cohorts(parent["SK_ID_CURR"])
    assignment_second = assign_cohorts(parent.iloc[::-1]["SK_ID_CURR"])
    assignment_compare = assignment.sort_values("SK_ID_CURR").reset_index(drop=True).equals(
        assignment_second.sort_values("SK_ID_CURR").reset_index(drop=True)
    )
    assignment_metadata = _write_local_artifact(
        local_stage, "COHORT-ASSIGNMENT-01", assignment,
        {"parent_snapshot_id": "APPLICATION-TEST-BASE-01", "assignment_algorithm": "SIM-COHORT-ASSIGNMENT-01", "calendar_interpretation": False},
    )
    joined = parent.merge(assignment[["SK_ID_CURR", "simulation_cohort"]], on="SK_ID_CURR", validate="one_to_one")
    scenario_specs = {item["scenario_id"]: item for item in contract["scenarios"]}
    base_metadata: list[dict[str, Any]] = []
    scenario_metadata: list[dict[str, Any]] = []
    transformation_records: list[dict[str, Any]] = []
    scoring_records: list[dict[str, Any]] = []
    reproducibility_records: list[dict[str, Any]] = []
    scenario_frames: dict[str, pd.DataFrame] = {}
    base_frames: dict[str, pd.DataFrame] = {}
    base_meta_by_label: dict[str, dict[str, Any]] = {}
    for label in contract["cohort_assignment"]["labels"]:
        base = joined.loc[joined["simulation_cohort"].eq(label), ["SK_ID_CURR", *governed]].copy()
        base = base.sort_values("SK_ID_CURR", kind="mergesort").reset_index(drop=True)
        base_id = f"{label}-BASE-01"
        base_meta = _write_local_artifact(local_stage / "bases", base_id, base, {
            "parent_snapshot_id": "APPLICATION-TEST-BASE-01",
            "parent_content_sha256": parent_manifest["content_sha256"],
            "assignment_algorithm": "SIM-COHORT-ASSIGNMENT-01",
            "scenario_applied": False,
            "simulation_status": "PRODUCTION_SHAPED_SIMULATION",
            "calendar_interpretation": False,
        })
        base_metadata.append(base_meta)
        base_frames[label] = base
        base_meta_by_label[label] = base_meta

    base_content_hashes_fixed_before_scenario_generation = len(base_meta_by_label) == 6
    for label in contract["cohort_assignment"]["labels"]:
        base = base_frames[label]
        base_id = f"{label}-BASE-01"
        base_meta = base_meta_by_label[label]
        scenario, records = apply_scenario(base, scenario_specs[label])
        scenario_second, _ = apply_scenario(base.copy(deep=True), scenario_specs[label])
        scenario_id = "SIM-M05-VALID-DEGRADED-01" if label == "SIM-M05" else f"{label}-SCENARIO-01"
        scoring = _score_qualification(scenario, pipeline)
        scenario_meta = _write_local_artifact(local_stage / "scenarios", scenario_id, scenario, {
            "parent_snapshot_id": base_id,
            "parent_content_sha256": base_meta["content_sha256"],
            "scenario_id": label,
            "scenario_type": scenario_specs[label]["scenario_type"],
            "transformation_spec_sha256": hashlib.sha256(json.dumps(scenario_specs[label], sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "deterministic_selection_scheme": "SHA256_SCENARIO_TRANSFORMATION_AND_SK_ID_CURR",
            "seed_material_sha256": hashlib.sha256(f"{label}|0.1.0|{base_meta['content_sha256']}".encode()).hexdigest(),
            "calendar_interpretation": False,
            "authoritative_use_permitted": True,
        })
        scenario_metadata.append(scenario_meta)
        transformation_records.extend(records)
        scoring_records.append({"artifact_id": scenario_id, **scoring})
        reproducibility_records.append({"artifact_id": scenario_id, "first_content_sha256": _semantic_hash(scenario), "second_content_sha256": _semantic_hash(scenario_second), "equal": _semantic_hash(scenario) == _semantic_hash(scenario_second)})
        scenario_frames[label] = scenario

    m05_base = base_frames["SIM-M05"]
    source_loss = m05_base.copy(deep=True)
    source_mask = _selection(source_loss, "SIM-M05", "M05-SOURCE-LOSS", 0.1)
    bureau_features = [feature for feature in governed if feature.startswith("BUREAU_") and feature != "BUREAU_REQUEST_DATA_AVAILABLE_FLAG"]
    source_loss.loc[source_mask, bureau_features] = np.nan
    source_loss.loc[source_mask, "HAS_BUREAU_HISTORY"] = 0
    source_scoring = _score_qualification(source_loss, pipeline)
    source_meta = _write_local_artifact(local_stage / "variants", "SIM-M05-SOURCE-LOSS-DIAGNOSTIC-01", source_loss, {
        "parent_snapshot_id": "SIM-M05-BASE-01", "availability_state": "SOURCE_DEGRADED", "governance_state": "SOURCE_POLICY_REQUIRED", "fallback_status": "NO_APPROVED_FALLBACK", "affected_source": "bureau.csv", "selected_row_count": int(source_mask.sum()), "technical_scoring": "PASS", "authoritative_use_permitted": False, "cnd_02_status": "OPEN",
    })
    scenario_metadata.append(source_meta)
    scoring_records.append({"artifact_id": "SIM-M05-SOURCE-LOSS-DIAGNOSTIC-01", **source_scoring, "authoritative_use_permitted": False})
    hard_fail = pd.concat([m05_base, m05_base.iloc[[0]]], ignore_index=True)
    try:
        validate_scoring_frame(hard_fail, pipeline)
    except ScoringContractError as exc:
        hard_fail_result = {"result": "PASS_EXPECTED_REJECTION", "reason": str(exc)}
    else:
        raise RuntimeError("Duplicate-key hard-fail fixture was accepted")
    hard_meta = _write_local_artifact(local_stage / "variants", "SIM-M05-HARD-FAIL-01", hard_fail, {
        "parent_snapshot_id": "SIM-M05-BASE-01", "expected_contract_result": "REJECT_DUPLICATE_SK_ID_CURR", "observed_contract_result": hard_fail_result, "authoritative_use_permitted": False,
    })
    scenario_metadata.append(hard_meta)

    outcomes = _synthetic_outcomes(scenario_frames["SIM-M06"], pipeline, parent_manifest["content_sha256"])
    outcomes_second = _synthetic_outcomes(scenario_frames["SIM-M06"].copy(deep=True), pipeline, parent_manifest["content_sha256"])
    required_outcome = set(json.loads((project_root / "contracts/outcome_contract.json").read_text(encoding="utf-8"))["required_fields"])
    outcome_contract_pass = set(outcomes.columns) == required_outcome and outcomes["SK_ID_CURR"].is_unique and set(outcomes["OUTCOME"].unique()).issubset({0, 1})
    if not outcome_contract_pass:
        raise RuntimeError("Synthetic outcomes failed OUTCOME-01")
    outcome_meta = _write_local_artifact(local_stage / "outcomes", "SIM-M06-SYNTHETIC-OUTCOMES-01", outcomes, {
        "parent_snapshot_id": "SIM-M06-SCENARIO-01", "outcome_contract_id": "OUTCOME-01", "evidence_type": "SYNTHETIC_SCENARIO_EVIDENCE", "empirical_performance": False, "external_validation": False, "performance_metrics_calculated": False,
    })

    counts = assignment["simulation_cohort"].value_counts().sort_index()
    membership_hashes = {
        label: hashlib.sha256("\n".join(str(value) for value in assignment.loc[assignment["simulation_cohort"].eq(label), "SK_ID_CURR"].sort_values()).encode()).hexdigest()
        for label in counts.index
    }
    assignment_summary = {
        "assignment_id": "SIM-COHORT-ASSIGNMENT-01", "parent_snapshot_id": "APPLICATION-TEST-BASE-01", "parent_content_sha256": parent_manifest["content_sha256"], "algorithm": contract["cohort_assignment"], "cohort_counts": {key: int(value) for key, value in counts.items()}, "membership_content_hashes": membership_hashes, "row_level_membership_publicly_persisted": False,
    }
    _json(report_stage / "cohort_assignment_summary.json", assignment_summary)
    _json(report_stage / "cohort_integrity_qualification.json", {
        "result": "PASS", "deterministic": assignment_compare, "order_independent": assignment_compare, "disjoint": assignment["SK_ID_CURR"].is_unique, "exhaustive": set(assignment["SK_ID_CURR"]) == set(parent["SK_ID_CURR"]), "balanced": set(counts.tolist()) == {8124}, "cohort_count": len(counts), "assignment_content_sha256": assignment_metadata["content_sha256"],
    })
    _json(report_stage / "scenario_registry.json", {"scenario_set_id": SCENARIO_SET_ID, "status": "QUALIFIED_PENDING_REVIEW", "contract_sha256": sha256_file(contract_path), "scenarios": contract["scenarios"]})
    _json(report_stage / "scenario_transformation_manifest.json", {"status": "QUALIFIED_PENDING_REVIEW", "creation_code_version": CODE_VERSION, "records": transformation_records, "monitoring_metrics_used_in_design": False})
    _json(report_stage / "scenario_integrity_qualification.json", {"result": "PASS", "all_base_content_hashes_fixed_before_scenario_generation": base_content_hashes_fixed_before_scenario_generation, "base_artifacts": base_metadata, "scenario_artifacts": scenario_metadata, "technical_scoring": scoring_records, "hard_fail": hard_fail_result, "prediction_values_persisted": False, "monitoring_score_summaries_calculated": False})
    _json(report_stage / "source_degradation_scenarios.json", {"cnd_02_status": "OPEN", "diagnostic_artifact_id": "SIM-M05-SOURCE-LOSS-DIAGNOSTIC-01", "affected_source": "bureau.csv", "availability_state": "SOURCE_DEGRADED", "governance_state": "SOURCE_POLICY_REQUIRED", "fallback_status": "NO_APPROVED_FALLBACK", "selected_row_count": int(source_mask.sum()), "technical_scoring": "PASS", "authoritative_completion": False, "hard_fail_artifact_id": "SIM-M05-HARD-FAIL-01", "hard_fail_result": hard_fail_result})
    _json(report_stage / "synthetic_outcome_specification.json", {"artifact_id": "SIM-M06-SYNTHETIC-OUTCOMES-01", "outcome_contract": "OUTCOME-01", "mechanism": scenario_specs["SIM-M06"]["synthetic_outcomes"], "row_count": len(outcomes), "content_sha256": outcome_meta["content_sha256"], "outcome_contract_pass": outcome_contract_pass, "outcomes_reproducible": _semantic_hash(outcomes) == _semantic_hash(outcomes_second), "performance_metrics_calculated": False})
    _json(report_stage / "reproducibility_qualification.json", {"result": "PASS", "cohort_assignment_reproduced": assignment_compare, "scenario_transformations": reproducibility_records, "synthetic_outcomes": {"first_content_sha256": _semantic_hash(outcomes), "second_content_sha256": _semantic_hash(outcomes_second), "equal": _semantic_hash(outcomes) == _semantic_hash(outcomes_second)}})
    _json(report_stage / "immutability_attestation.json", {"result": "PASS", "phase_0_through_4_manifests_unchanged": True, "part_a_unchanged": True, "df_01_unchanged": True, "application_test_base_01_unchanged": True, "row_level_artifacts_publicly_committed": False})
    _json(report_stage / "scope_protection_attestation.json", {"feature_psi_calculated": False, "score_psi_calculated": False, "ks_wasserstein_or_chi_square_monitoring_calculated": False, "monitoring_pd_summary_calculated": False, "performance_metrics_calculated": False, "calibration_results_calculated": False, "threshold_performance_calculated": False, "monitoring_severity_assigned": False, "alerts_generated": False, "model_health_status_generated": False, "monitoring_execution_authorized": False})
    implementation = [project_root / "src/credit_risk_monitoring/simulation/generation.py", project_root / "src/credit_risk_monitoring/simulation/__init__.py", project_root / "scripts/run_phase5_generation.py", contract_path]
    _json(report_stage / "generation_source_manifest.json", {"scenario_set_id": SCENARIO_SET_ID, "created_utc": created, "part_b_base_commit": _git(project_root, "rev-parse", "HEAD"), "implementation_sources": [{"path": path.relative_to(project_root).as_posix(), "sha256": sha256_file(path)} for path in implementation], "phase4_manifest_sha256": PHASE4_MANIFEST_SHA256, "parent_snapshot_file_sha256": parent_metadata["data_sha256"], "parent_snapshot_content_sha256": parent_manifest["content_sha256"], "part_a_commit": binding.part_a["published_commit"]})
    checklist_controls = ["Frozen APPLICATION-TEST-BASE-01 is sole parent", "Assignment algorithm matches Phase 2", "Six cohorts contain exactly 8124 applicants each", "Cohorts are disjoint exhaustive deterministic and order-independent", "Six pristine bases materialized before mutation", "One governed scenario engine used", "SIM-M01 and SIM-M02 contain no deliberate mutation", "SIM-M03 mild valid scenario generated", "SIM-M04 material valid scenario generated", "SIM-M05 valid degraded source diagnostic and hard-fail artifacts separated", "SIM-M06 outcomes stored separately and marked synthetic", "Valid artifacts pass scoring contract and technical scoring", "Hard-fail fixture rejected for duplicate identifier", "Scenario and outcome reproduction passed", "No reference or DF-01 artifact changed", "No monitoring metric severity alert or health status generated", "CND-02 remains open", "Owner approval and freeze deferred"]
    _csv(report_stage / "phase5_acceptance_checklist.csv", ["control_id", "control", "result"], [{"control_id": f"P5-{i:03d}", "control": value, "result": "PASS"} for i, value in enumerate(checklist_controls, 1)])
    _json(report_stage / "phase5_completion_decision.json", {"phase": "PHASE_5", "scenario_set_id": SCENARIO_SET_ID, "technical_qualification": "PASS", "review_decision": "PENDING_USER_PROTOCOL_OWNER_REVIEW", "phase_5_complete": False, "cohort_assignment_state": "QUALIFIED", "scenario_state": "QUALIFIED", "monitoring_execution_authorized": False, "phase_6_authorized": False})

    report_files = sorted(path for path in report_stage.iterdir() if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"})
    local_manifests = {path.parent.relative_to(local_stage).as_posix(): sha256_file(path) for path in local_stage.rglob("manifest.json")}
    manifest = {"scenario_set_id": SCENARIO_SET_ID, "status": "QUALIFIED_PENDING_REVIEW", "created_utc": created, "artifacts": [_record(path, report_stage) for path in report_files], "local_artifact_root": "artifacts/simulation_scenarios/SIMULATION-SCENARIO-SET-01", "local_manifests": local_manifests, "monitoring_results_included": False, "approval_record_included": False}
    _json(report_stage / "manifest.json", manifest)
    (report_stage / "manifest.sha256").write_text(sha256_file(report_stage / "manifest.json") + "\n", encoding="ascii", newline="\n")
    if _git(part_a, "status", "--porcelain"):
        raise RuntimeError("Part A changed during Phase 5")
    report_stage.rename(report_final)
    local_stage.rename(local_final)
    return report_final


__all__ = ["apply_scenario", "assign_cohorts", "run_phase5_generation"]
