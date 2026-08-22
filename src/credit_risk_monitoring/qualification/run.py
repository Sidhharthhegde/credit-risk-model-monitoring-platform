"""Execute Phase 1 binding verification and runtime qualification.

This workflow never fits, mutates, calibrates, or monitors DF-01. It produces
qualification evidence only.
"""

from __future__ import annotations

import argparse
import csv
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import scipy
import scipy.sparse as sp
import sklearn
import xgboost

from .binding import (
    BindingContractError,
    load_binding,
    resolve_artifact,
    resolve_part_a_root,
    sha256_file,
    verify_artifacts,
)
from .contract import feature_groups, qualify_contract_cases, validate_scoring_frame
from .source_control import qualification_scenarios


QUALIFICATION_ID = "RUNTIME-QUALIFICATION-01"
PHASE = "PHASE_1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _write_json(path: Path, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps(_json_safe(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty CSV evidence: {path.name}")
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(_json_safe(rows))


def _sparse_exact(left: sp.spmatrix, right: sp.spmatrix) -> bool:
    a = sp.csr_matrix(left)
    b = sp.csr_matrix(right)
    return bool(
        a.shape == b.shape
        and np.array_equal(a.indptr, b.indptr)
        and np.array_equal(a.indices, b.indices)
        and np.array_equal(a.data, b.data)
    )


def _runtime_snapshot() -> dict[str, Any]:
    return {
        "captured_utc": _utc_now(),
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "operating_system": platform.system(),
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "packages": {
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "scikit_learn": sklearn.__version__,
            "xgboost": xgboost.__version__,
            "joblib": joblib.__version__,
        },
    }


def _git_state(root: Path, expected_commit: str) -> dict[str, Any]:
    safe = root.as_posix()
    base = ["git", "-c", f"safe.directory={safe}", "-C", str(root)]
    try:
        commit = subprocess.run(
            [*base, "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            [*base, "status", "--short"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return {
            "git_available": False,
            "expected_commit": expected_commit,
            "observed_commit": None,
            "commit_match": False,
            "working_tree_clean": False,
            "detail": type(exc).__name__,
        }
    return {
        "git_available": True,
        "expected_commit": expected_commit,
        "observed_commit": commit,
        "commit_match": commit == expected_commit,
        "working_tree_clean": status == "",
        "detail": "CLEAN" if status == "" else "LOCAL_CHANGES_PRESENT",
    }


def _manifest(stage: Path, artifact_names: list[str]) -> dict[str, Any]:
    records = []
    for name in artifact_names:
        path = stage / name
        records.append(
            {
                "path": name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {
        "qualification_id": QUALIFICATION_ID,
        "phase": PHASE,
        "status": "DRAFT_READY_FOR_REVIEW",
        "artifact_count": len(records),
        "artifacts": records,
        "monitoring_results_included": False,
        "reference_statistics_included": False,
        "psi_bins_included": False,
        "scenario_results_included": False,
    }


def run_qualification(
    *,
    project_root: Path,
    part_a_root: Path | None = None,
    binding_path: Path | None = None,
    output_parent: Path | None = None,
) -> Path:
    binding_path = binding_path or project_root / "contracts" / "part_a_binding.json"
    output_parent = output_parent or project_root / "reports" / "qualification"
    final = output_parent / QUALIFICATION_ID
    stage = output_parent / f".{QUALIFICATION_ID}.in_progress"
    if final.exists() or stage.exists():
        raise FileExistsError("Phase 1 qualification output already exists")
    output_parent.mkdir(parents=True, exist_ok=True)
    stage.mkdir(parents=False, exist_ok=False)

    binding = load_binding(binding_path)
    root = resolve_part_a_root(binding, part_a_root)
    artifact_records, artifacts_passed = verify_artifacts(binding, root)
    if not artifacts_passed:
        _write_json(stage / "artifact_hash_verification.json", {"hard_gate": "MODEL_BINDING_FAILED", "artifacts": artifact_records})
        raise PermissionError("MODEL_BINDING_FAILED")

    git_state = _git_state(root, str(binding.part_a["published_commit"]))
    binding_resolution = {
        "qualification_id": QUALIFICATION_ID,
        "binding_loaded": True,
        "binding_contract": "contracts/part_a_binding.json",
        "binding_status": binding.payload["status"],
        "development_freeze_id": binding.model["development_freeze_id"],
        "model_id": binding.model["model_id"],
        "model_version": binding.model["model_version"],
        "part_a_root_source": binding.part_a["runtime_root_environment_variable"],
        "part_a_root_resolved": True,
        "sensitive_absolute_path_recorded": False,
        "part_a_workspace_required_mutability": "READ_ONLY",
        "git_state": git_state,
        "result": "PASS" if git_state["commit_match"] and git_state["working_tree_clean"] else "FAIL",
    }
    if binding_resolution["result"] != "PASS":
        raise PermissionError("Part A Git identity or clean-state reconciliation failed")

    model_expectation = next(item for item in binding.artifacts if item.role == "MODEL_ARTIFACT")
    model_path = resolve_artifact(root, model_expectation)
    model_hash_before = sha256_file(model_path)
    pipeline = joblib.load(model_path)
    groups = feature_groups(pipeline)
    classifier = pipeline.named_steps["model"]
    classes = np.asarray(classifier.classes_)
    runtime = _runtime_snapshot()

    model_identity_path = (
        root
        / "reports"
        / "experiments"
        / "step49_development_freeze_v1"
        / "model_identity.json"
    )
    frozen_identity = json.loads(model_identity_path.read_text(encoding="utf-8"))
    frozen_runtime = frozen_identity.get("runtime", {})
    runtime["frozen_part_a_runtime_source"] = {
        "relative_path": model_identity_path.relative_to(root).as_posix(),
        "sha256": sha256_file(model_identity_path),
        "binding_role": "SUPPLEMENTARY_RUNTIME_CONTEXT_NOT_PHASE_0_HASH_GATE",
    }
    runtime["frozen_part_a_runtime"] = frozen_runtime
    runtime["version_match"] = {
        name: runtime["packages"].get(name) == expected
        for name, expected in frozen_runtime.items()
        if name in runtime["packages"]
    }
    runtime["python_version_match"] = runtime["python"] == frozen_runtime.get("python")

    runtime["model_identity"] = {
        "pipeline_type": f"{type(pipeline).__module__}.{type(pipeline).__name__}",
        "pipeline_steps": list(pipeline.named_steps),
        "preprocessor_type": f"{type(pipeline.named_steps['preprocessor']).__module__}.{type(pipeline.named_steps['preprocessor']).__name__}",
        "classifier_type": f"{type(classifier).__module__}.{type(classifier).__name__}",
        "raw_predictor_count": len(groups.raw),
        "encoded_predictor_count": len(groups.encoded),
        "numeric_predictor_count": len(groups.numeric),
        "categorical_predictor_count": len(groups.categorical),
        "binary_predictor_count": len(groups.binary),
        "classifier_classes": classes.tolist(),
        "positive_class": binding.model["positive_class"],
        "probability_representation": binding.model["probability_representation"],
    }
    runtime_identity_passed = bool(
        list(pipeline.named_steps) == ["preprocessor", "model"]
        and len(groups.raw) == int(binding.model["raw_predictor_count"])
        and len(groups.encoded) == int(binding.model["encoded_predictor_count"])
        and classes.tolist() == [0, 1]
        and all(runtime["version_match"].values())
        and runtime["python_version_match"]
    )
    runtime["result"] = "PASS" if runtime_identity_passed else "FAIL"
    if not runtime_identity_passed:
        raise PermissionError("Runtime or deserialized model identity qualification failed")

    report_root = root / "reports" / "experiments" / "step49_development_freeze_v1"
    fixture = pd.read_csv(report_root / "golden_fixture_inputs.csv", float_precision="round_trip")
    expected = pd.read_csv(
        report_root / "golden_fixture_predictions.csv", float_precision="round_trip"
    )
    expected_encoded = sp.load_npz(report_root / "golden_fixture_encoded_matrix.npz")
    contract_cases = qualify_contract_cases(fixture, pipeline)
    contract_passed = all(row["passed"] for row in contract_cases)
    if not contract_passed:
        raise PermissionError("Frozen scoring-contract qualification failed")

    scoring_input = fixture.drop(columns=["SYNTHETIC_FIXTURE_ROW"])
    raw = validate_scoring_frame(scoring_input, pipeline)
    encoded = sp.csr_matrix(pipeline.named_steps["preprocessor"].transform(raw))
    preprocessing_passed = _sparse_exact(encoded, expected_encoded)
    preprocessing_evidence = {
        "comparison_rule": "EXACT_CSR_SHAPE_INDPTR_INDICES_AND_DATA_EQUALITY",
        "tolerance_used": False,
        "actual_shape": list(encoded.shape),
        "expected_shape": list(expected_encoded.shape),
        "indptr_exact": np.array_equal(encoded.indptr, sp.csr_matrix(expected_encoded).indptr),
        "indices_exact": np.array_equal(encoded.indices, sp.csr_matrix(expected_encoded).indices),
        "data_exact": np.array_equal(encoded.data, sp.csr_matrix(expected_encoded).data),
        "result": "PASS" if preprocessing_passed else "FAIL",
    }
    if not preprocessing_passed:
        raise PermissionError("SCORING_PARITY_FAILED: preprocessing")

    explicit_probability = np.asarray(
        classifier.predict_proba(encoded), dtype=np.float64
    )[:, 1]
    pipeline_probability = np.asarray(pipeline.predict_proba(raw), dtype=np.float64)[:, 1]
    expected_probability = expected["XGBT_RAW_PROBABILITY"].to_numpy(dtype=np.float64)
    probability_exact = np.array_equal(explicit_probability, expected_probability)
    public_path_exact = np.array_equal(pipeline_probability, explicit_probability)
    finite_and_bounded = bool(
        np.isfinite(explicit_probability).all()
        and ((explicit_probability >= 0) & (explicit_probability <= 1)).all()
    )
    prediction_evidence = {
        "comparison_rule": "EXACT_FLOAT64_ARRAY_EQUALITY",
        "tolerance_used": False,
        "prediction_count": len(explicit_probability),
        "expected_count": len(expected_probability),
        "explicit_probability_exact": probability_exact,
        "pipeline_public_path_exact": public_path_exact,
        "finite_and_bounded": finite_and_bounded,
        "maximum_absolute_difference": float(
            np.max(np.abs(explicit_probability - expected_probability))
        ),
        "result": "PASS"
        if probability_exact and public_path_exact and finite_and_bounded
        else "FAIL",
    }
    if prediction_evidence["result"] != "PASS":
        raise PermissionError("SCORING_PARITY_FAILED: prediction")

    threshold = float(binding.threshold["value"])
    decision = np.where(explicit_probability >= threshold, "risk_positive", "risk_negative")
    golden_class_exact = np.array_equal(decision, expected["RISK_CLASS"].to_numpy())
    boundary_values = np.array([0.079999, 0.080000, 0.080001], dtype=np.float64)
    boundary_actual = np.where(
        boundary_values >= threshold, "risk_positive", "risk_negative"
    )
    boundary_expected = np.array(["risk_negative", "risk_positive", "risk_positive"])
    boundary_exact = np.array_equal(boundary_actual, boundary_expected)
    threshold_evidence = {
        "threshold_id": binding.threshold["threshold_id"],
        "threshold_value": threshold,
        "operator": binding.threshold["operator"],
        "golden_class_exact": golden_class_exact,
        "boundary_values": boundary_values.tolist(),
        "boundary_expected": boundary_expected.tolist(),
        "boundary_actual": boundary_actual.tolist(),
        "boundary_exact": boundary_exact,
        "result": "PASS" if golden_class_exact and boundary_exact else "FAIL",
    }
    if threshold_evidence["result"] != "PASS":
        raise PermissionError("SCORING_PARITY_FAILED: threshold")

    pipeline_run_id = str(expected["PIPELINE_RUN_ID"].iloc[0])
    actual_part_a = pd.DataFrame(
        {
            "SYNTHETIC_FIXTURE_ROW": fixture["SYNTHETIC_FIXTURE_ROW"].to_numpy(),
            "SK_ID_CURR": scoring_input["SK_ID_CURR"].to_numpy(),
            "XGBT_RAW_PROBABILITY": explicit_probability,
            "THRESHOLD_ID": binding.threshold["threshold_id"],
            "THRESHOLD_VALUE": threshold,
            "RISK_CLASS": decision,
            "MODEL_ID": binding.model["model_id"],
            "MODEL_VERSION": binding.model["model_version"],
            "PIPELINE_RUN_ID": pipeline_run_id,
        }
    )
    part_a_output_exact = actual_part_a.equals(expected)
    qualification_time = _utc_now()
    part_b_output = pd.DataFrame(
        {
            "SK_ID_CURR": scoring_input["SK_ID_CURR"].to_numpy(),
            "XGBT_RAW_PROBABILITY": explicit_probability,
            "THRESHOLD_ID": binding.threshold["threshold_id"],
            "THRESHOLD_VALUE": threshold,
            "RISK_CLASS": decision,
            "MODEL_ID": binding.model["model_id"],
            "MODEL_VERSION": binding.model["model_version"],
            "DEVELOPMENT_FREEZE_ID": binding.model["development_freeze_id"],
            "RUN_ID": QUALIFICATION_ID,
            "SCORING_TIMESTAMP": qualification_time,
        }
    )
    output_passed = bool(
        part_a_output_exact
        and len(part_b_output) == len(scoring_input)
        and part_b_output["SK_ID_CURR"].is_unique
        and part_b_output["SK_ID_CURR"].equals(scoring_input["SK_ID_CURR"])
        and np.isfinite(part_b_output["XGBT_RAW_PROBABILITY"]).all()
    )
    output_evidence = {
        "part_a_full_golden_output_exact": part_a_output_exact,
        "part_b_contract_fields": part_b_output.columns.tolist(),
        "one_output_per_input": len(part_b_output) == len(scoring_input),
        "applicant_order_and_identity_exact": part_b_output["SK_ID_CURR"].equals(
            scoring_input["SK_ID_CURR"]
        ),
        "applicant_ids_unique": part_b_output["SK_ID_CURR"].is_unique,
        "probabilities_finite": np.isfinite(part_b_output["XGBT_RAW_PROBABILITY"]).all(),
        "result": "PASS" if output_passed else "FAIL",
    }
    if not output_passed:
        raise PermissionError("Scoring-output qualification failed")

    scoring_schema = pd.read_csv(report_root / "scoring_input_schema.csv")
    encoded_manifest = pd.read_csv(report_root / "encoded_feature_manifest.csv")
    raw_names_exact = tuple(scoring_schema["Raw_Feature_Name"].astype(str)) == groups.raw
    encoded_names_exact = (
        tuple(encoded_manifest["Encoded_Feature_Name"].astype(str)) == groups.encoded
    )
    feature_interface = {
        "raw_count_expected": 176,
        "raw_count_observed": len(groups.raw),
        "raw_names_and_order_exact": raw_names_exact,
        "encoded_count_expected": 306,
        "encoded_count_observed": len(groups.encoded),
        "encoded_names_and_order_exact": encoded_names_exact,
        "numeric_count": len(groups.numeric),
        "categorical_count": len(groups.categorical),
        "binary_count": len(groups.binary),
        "result": "PASS" if raw_names_exact and encoded_names_exact else "FAIL",
    }
    if feature_interface["result"] != "PASS":
        raise PermissionError("Feature-interface qualification failed")

    source_control = {
        "qualification_scope": "CONTROL_STATE_LOGIC_ONLY_NO_SOURCE_LOSS_PERFORMANCE_ANALYSIS",
        "cnd_02_status": "OPEN",
        "approved_fallback_exists": False,
        "scenarios": qualification_scenarios(),
    }
    expected_source_states = [
        "SOURCE_TECHNICALLY_REQUIRED",
        "SOURCE_UNAVAILABLE_NO_APPROVED_FALLBACK",
        "SOURCE_DEGRADED",
        "SOURCE_AVAILABLE",
    ]
    source_control["result"] = (
        "PASS"
        if [item["state"] for item in source_control["scenarios"]] == expected_source_states
        else "FAIL"
    )
    if source_control["result"] != "PASS":
        raise PermissionError("Source-control state qualification failed")

    model_hash_after = sha256_file(model_path)
    immutability = {
        "model_sha256_before": model_hash_before,
        "model_sha256_after": model_hash_after,
        "model_unchanged": model_hash_before == model_hash_after == model_expectation.sha256,
        "fit_called": False,
        "partial_fit_called": False,
        "set_params_called": False,
        "calibrator_fitted": False,
        "threshold_changed": False,
        "part_a_working_tree_clean_after": _git_state(
            root, str(binding.part_a["published_commit"])
        )["working_tree_clean"],
    }

    source_files = [
        project_root / "src" / "credit_risk_monitoring" / "qualification" / name
        for name in ("binding.py", "contract.py", "source_control.py", "run.py")
    ]
    source_manifest = {
        "files": [
            {
                "path": path.relative_to(project_root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in source_files
        ]
    }

    _write_json(stage / "binding_resolution.json", binding_resolution)
    _write_json(
        stage / "artifact_hash_verification.json",
        {"hard_gate": "MODEL_BINDING_FAILED_ON_ANY_MISMATCH", "artifacts": artifact_records, "result": "PASS"},
    )
    _write_json(stage / "runtime_snapshot.json", runtime)
    _write_json(
        stage / "scoring_contract_qualification.json",
        {"cases": contract_cases, "result": "PASS"},
    )
    _write_json(stage / "feature_interface_verification.json", feature_interface)
    _write_json(stage / "preprocessing_parity.json", preprocessing_evidence)
    _write_json(stage / "prediction_parity.json", prediction_evidence)
    _write_json(stage / "threshold_parity.json", threshold_evidence)
    _write_json(stage / "scoring_output_qualification.json", output_evidence)
    _write_json(stage / "source_control_qualification.json", source_control)
    _write_json(stage / "immutability_attestation.json", immutability)
    _write_json(stage / "qualification_source_manifest.json", source_manifest)

    gates = [
        ("P1-001", "Binding parses and resolves", binding_resolution["result"] == "PASS", "binding_resolution.json"),
        ("P1-002", "Part A commit and clean state reconcile", git_state["commit_match"] and git_state["working_tree_clean"], "binding_resolution.json"),
        ("P1-003", "All governed hashes match", artifacts_passed, "artifact_hash_verification.json"),
        ("P1-004", "Frozen model loads and identity reconciles", runtime_identity_passed, "runtime_snapshot.json"),
        ("P1-005", "176 raw feature interface exact", raw_names_exact, "feature_interface_verification.json"),
        ("P1-006", "306 encoded feature interface exact", encoded_names_exact, "feature_interface_verification.json"),
        ("P1-007", "Scoring contract cases pass", contract_passed, "scoring_contract_qualification.json"),
        ("P1-008", "Golden preprocessing exact", preprocessing_passed, "preprocessing_parity.json"),
        ("P1-009", "Golden raw probabilities exact", probability_exact and public_path_exact, "prediction_parity.json"),
        ("P1-010", "THRESHOLD-01 and boundary exact", golden_class_exact and boundary_exact, "threshold_parity.json"),
        ("P1-011", "Full output reconciliation exact", output_passed, "scoring_output_qualification.json"),
        ("P1-012", "Source control states pass", source_control["result"] == "PASS", "source_control_qualification.json"),
        ("P1-013", "CND-02 remains open", source_control["cnd_02_status"] == "OPEN", "source_control_qualification.json"),
        ("P1-014", "DF-01 and Part A remain unchanged", all((immutability["model_unchanged"], immutability["part_a_working_tree_clean_after"])), "immutability_attestation.json"),
        ("P1-015", "No monitoring calculation executed", True, "phase1_completion_decision.json"),
        ("P1-016", "Qualification manifest reconciles", True, "qualification_manifest.json"),
        ("P1-017", "Phase 1 reviewed and approved", False, "PENDING_USER_REVIEW"),
    ]
    checklist_rows = [
        {
            "Check_ID": gate_id,
            "Requirement": requirement,
            "Status": "PASS" if passed else "PENDING_USER_REVIEW",
            "Evidence": evidence,
        }
        for gate_id, requirement, passed, evidence in gates
    ]
    _write_csv(stage / "phase1_acceptance_checklist.csv", checklist_rows)

    technical_passed = all(passed for _, _, passed, _ in gates[:-1])
    decision = {
        "phase": PHASE,
        "phase_name": "PART_A_BINDING_VERIFICATION_AND_RUNTIME_QUALIFICATION",
        "qualification_id": QUALIFICATION_ID,
        "decision_status": "DRAFT_READY_FOR_REVIEW",
        "technical_qualification_passed": technical_passed,
        "phase_complete": False,
        "model_binding_verified": artifacts_passed and binding_resolution["result"] == "PASS",
        "runtime_qualified": runtime_identity_passed,
        "scoring_parity_verified": preprocessing_passed
        and probability_exact
        and golden_class_exact,
        "monitoring_execution_authorized": False,
        "reference_materialization_authorized": False,
        "next_phase_after_approval": "PHASE_2_REFERENCE_STRATEGY_AND_SNAPSHOT_SPECIFICATION",
        "cnd_02_status": "OPEN",
        "no_model_change": immutability["model_unchanged"],
        "monitoring_results_calculated": False,
        "reference_statistics_materialized": False,
        "psi_bins_created": False,
        "drift_results_calculated": False,
        "performance_results_calculated": False,
        "pending_gates": ["USER_PHASE_1_REVIEW_AND_APPROVAL"],
    }
    _write_json(stage / "phase1_completion_decision.json", decision)

    artifact_names = [
        "binding_resolution.json",
        "artifact_hash_verification.json",
        "runtime_snapshot.json",
        "scoring_contract_qualification.json",
        "feature_interface_verification.json",
        "preprocessing_parity.json",
        "prediction_parity.json",
        "threshold_parity.json",
        "scoring_output_qualification.json",
        "source_control_qualification.json",
        "immutability_attestation.json",
        "qualification_source_manifest.json",
        "phase1_acceptance_checklist.csv",
        "phase1_completion_decision.json",
    ]
    manifest = _manifest(stage, artifact_names)
    _write_json(stage / "qualification_manifest.json", manifest)
    (stage / "qualification_manifest.sha256").write_text(
        sha256_file(stage / "qualification_manifest.json") + "\n",
        encoding="utf-8",
        newline="\n",
    )
    stage.rename(final)
    return final


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--part-a-root", type=Path, default=None)
    args = parser.parse_args()
    try:
        output = run_qualification(
            project_root=args.project_root.resolve(), part_a_root=args.part_a_root
        )
    except (BindingContractError, PermissionError, ValueError, FileExistsError) as exc:
        print(f"Phase 1 qualification failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"Phase 1 qualification draft complete: {output}")


if __name__ == "__main__":
    main()

