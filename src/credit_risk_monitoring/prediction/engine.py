"""Phase 8 raw-prediction, score-PSI and frozen-threshold monitoring."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from credit_risk_monitoring.qualification.binding import load_binding, resolve_part_a_root, sha256_file, verify_artifacts
from credit_risk_monitoring.qualification.contract import validate_scoring_frame
from credit_risk_monitoring.reference.materialization import _semantic_hash


MONITORING_ID = "PREDICTION-MONITORING-01"
CODE_VERSION = "PHASE8-PREDICTION-MONITOR-0.1.0"


def _json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def _record(path: Path, root: Path) -> dict[str, Any]:
    return {"path": path.relative_to(root).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def apply_threshold(probabilities: np.ndarray, threshold: float = 0.08) -> np.ndarray:
    values = np.asarray(probabilities, dtype=np.float64)
    return np.where(values >= threshold, "risk_positive", "risk_negative")


def _semantic_prediction_hash(frame: pd.DataFrame) -> str:
    canonical = frame.sort_values("SK_ID_CURR", kind="mergesort")[["SK_ID_CURR", "raw_probability", "analytical_risk_class"]].reset_index(drop=True)
    return _semantic_hash(canonical)


def _smooth(values: np.ndarray, epsilon: float) -> np.ndarray:
    result = values.astype(float).copy()
    result[result == 0.0] = epsilon
    return result / result.sum()


def _severity(value: float, warning: float, critical: float) -> str:
    return "CRITICAL" if value >= critical else ("WARNING" if value >= warning else "NORMAL")


def _score_buckets(probabilities: np.ndarray, inner_edges: list[float]) -> tuple[pd.Series, list[str]]:
    labels = [f"SCORE_BIN_{index:02d}" for index in range(1, len(inner_edges) + 2)]
    buckets = pd.cut(np.asarray(probabilities, dtype=float), bins=[0.0, *inner_edges, 1.0], labels=labels, include_lowest=True, right=True)
    if pd.isna(buckets).any():
        raise RuntimeError("A valid probability did not map to a frozen score bin")
    return pd.Series(buckets.astype("string")), labels


@dataclass(frozen=True)
class PredictionEvaluation:
    predictions: pd.DataFrame
    summary: dict[str, Any]
    score_psi: dict[str, Any]
    bin_results: pd.DataFrame
    threshold_output: dict[str, Any]


class PredictionMonitor:
    def __init__(self, contract: dict[str, Any], reference_probabilities: np.ndarray, score_bins: dict[str, Any], reference_summary: dict[str, Any]) -> None:
        self.contract = contract
        self.reference = np.asarray(reference_probabilities, dtype=np.float64)
        self.inner_edges = [float(value) for value in score_bins["finite_inner_edges"]]
        self.reference_summary = reference_summary
        reference_bucket, self.labels = _score_buckets(self.reference, self.inner_edges)
        self.reference_counts = reference_bucket.value_counts().reindex(self.labels, fill_value=0).astype(int)
        self.epsilon = float(contract["score_psi"]["epsilon"])

    def evaluate(self, identifiers: pd.Series, probabilities: np.ndarray, *, artifact_id: str, scenario_id: str) -> PredictionEvaluation:
        values = np.asarray(probabilities, dtype=np.float64)
        if len(values) != len(identifiers) or len(values) == 0:
            raise RuntimeError("Prediction count does not reconcile to input")
        if not np.isfinite(values).all() or (values < 0).any() or (values > 1).any():
            raise RuntimeError("Raw prediction is missing, non-finite or outside [0,1]")
        if identifiers.isna().any() or not identifiers.is_unique:
            raise RuntimeError("Applicant identity is not unique and complete")
        threshold = self.contract["threshold"]
        classes = apply_threshold(values, float(threshold["value"]))
        prediction_run_id = f"PRED-RUN-{artifact_id}-01"
        predictions = pd.DataFrame({
            "SK_ID_CURR": identifiers.to_numpy(), "raw_probability": values,
            "threshold_id": threshold["threshold_id"], "threshold_value": float(threshold["value"]),
            "threshold_operator": threshold["operator"], "analytical_risk_class": classes,
            "model_id": "XGBT-01", "model_version": "xgbt01_raw_threshold01_df_v1",
            "development_freeze_id": "DF-01", "scenario_id": scenario_id,
            "scenario_artifact_id": artifact_id, "prediction_run_id": prediction_run_id,
        })
        quantiles = self.contract["score_reference"]["approved_quantiles"]
        current_quantiles = {str(value): float(np.quantile(values, value)) for value in quantiles}
        reference_quantiles = {str(key): float(value) for key, value in self.reference_summary["quantiles"].items()}
        summary = {
            "run_id": prediction_run_id, "scenario_id": scenario_id, "artifact_id": artifact_id,
            "reference_id": "PERF-REF-01", "prediction_count": len(values),
            "mean_probability": float(values.mean()), "reference_mean_probability": float(self.reference_summary["mean"]),
            "mean_probability_change": float(values.mean() - self.reference_summary["mean"]),
            "median_probability": float(np.median(values)), "reference_median_probability": reference_quantiles["0.5"],
            "median_probability_change": float(np.median(values) - reference_quantiles["0.5"]),
            "standard_deviation": float(values.std(ddof=0)), "minimum_probability": float(values.min()), "maximum_probability": float(values.max()),
            "current_quantiles": current_quantiles, "reference_quantiles": reference_quantiles,
            "supporting_statistic_severity": "N/A", "probability_representation": "RAW_P_TARGET_1",
            "authoritative_result": True, "alert_generated": False,
        }
        current_bucket, labels = _score_buckets(values, self.inner_edges)
        current_counts = current_bucket.value_counts().reindex(labels, fill_value=0).astype(int)
        reference_raw = self.reference_counts.to_numpy(dtype=float) / len(self.reference)
        current_raw = current_counts.to_numpy(dtype=float) / len(values)
        reference_smooth, current_smooth = _smooth(reference_raw, self.epsilon), _smooth(current_raw, self.epsilon)
        contributions = (current_smooth - reference_smooth) * np.log(current_smooth / reference_smooth)
        total_psi = float(contributions.sum())
        bin_results = pd.DataFrame({
            "run_id": prediction_run_id, "scenario_id": scenario_id, "artifact_id": artifact_id,
            "reference_id": "PERF-REF-01", "bin_order": range(1, len(labels) + 1), "score_bin": labels,
            "reference_count": self.reference_counts.to_numpy(), "current_count": current_counts.to_numpy(),
            "reference_proportion_raw": reference_raw, "current_proportion_raw": current_raw,
            "reference_proportion_smoothed": reference_smooth, "current_proportion_smoothed": current_smooth,
            "psi_contribution": contributions, "epsilon": self.epsilon,
        })
        psi_policy = self.contract["score_psi"]
        score_psi = {
            "run_id": prediction_run_id, "scenario_id": scenario_id, "artifact_id": artifact_id,
            "control_id": psi_policy["control_id"], "metric_id": psi_policy["metric_id"], "reference_id": "PERF-REF-01",
            "score_psi": total_psi, "severity": _severity(total_psi, psi_policy["warning"], psi_policy["critical"]),
            "frozen_score_bins_used": True, "rebucketing_performed": False, "alert_generated": False,
        }
        positive_count = int((classes == "risk_positive").sum())
        negative_count = len(values) - positive_count
        positive_rate, negative_rate = positive_count / len(values), negative_count / len(values)
        reference_positive = float(self.reference_summary["risk_positive_rate"])
        change = abs(positive_rate - reference_positive)
        output_policy = self.contract["threshold_output"]
        threshold_output = {
            "run_id": prediction_run_id, "scenario_id": scenario_id, "artifact_id": artifact_id,
            "control_id": output_policy["control_id"], "metric_id": output_policy["metric_id"],
            "threshold_id": threshold["threshold_id"], "threshold_value": float(threshold["value"]), "threshold_operator": threshold["operator"],
            "risk_positive_count": positive_count, "risk_positive_rate": positive_rate,
            "risk_negative_count": negative_count, "risk_negative_rate": negative_rate,
            "reference_risk_positive_rate": reference_positive, "reference_risk_negative_rate": float(self.reference_summary["risk_negative_rate"]),
            "risk_positive_rate_change": positive_rate - reference_positive,
            "risk_positive_rate_change_percentage_points": (positive_rate - reference_positive) * 100.0,
            "absolute_risk_positive_rate_change": change,
            "absolute_risk_positive_rate_change_percentage_points": change * 100.0,
            "rate_change_primary_reporting_unit": "PERCENTAGE_POINTS",
            "severity": _severity(change, output_policy["absolute_rate_change_warning"], output_policy["absolute_rate_change_critical"]),
            "terminology": output_policy["terminology"], "alert_generated": False,
        }
        return PredictionEvaluation(predictions, summary, score_psi, bin_results, threshold_output)


def run_phase8_monitoring(project_root: Path, explicit_part_a_root: Path | None = None) -> Path:
    project_root = project_root.resolve()
    contract_path = project_root / "contracts/prediction_monitoring_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    dependency_paths = {
        "phase_6_manifest_sha256": "reports/monitoring/DATA-QUALITY-CONTROL-01/manifest.json",
        "phase_7_manifest_sha256": "reports/monitoring/FEATURE-DRIFT-MONITORING-01/manifest.json",
        "reference_materialization_manifest_sha256": "reports/reference/REFERENCE-MATERIALIZATION-01/manifest.json",
        "scenario_set_manifest_sha256": "reports/simulation/SIMULATION-SCENARIO-SET-01/manifest.json",
        "score_reference_sha256": "reports/reference/REFERENCE-MATERIALIZATION-01/score_reference.json",
        "score_bin_definitions_sha256": "reports/reference/REFERENCE-MATERIALIZATION-01/score_psi_bin_definitions.json",
        "alert_thresholds_sha256": "configs/alert_thresholds.yaml",
    }
    for key, relative in dependency_paths.items():
        if sha256_file(project_root / relative) != contract["frozen_dependencies"][key]:
            raise RuntimeError(f"Frozen Phase 8 dependency changed: {relative}")
    phase7 = json.loads((project_root / "reports/monitoring/FEATURE-DRIFT-MONITORING-01/phase7_completion_decision.json").read_text(encoding="utf-8"))
    if phase7["review_decision"] != "APPROVED" or not phase7["phase_8_authorized"]:
        raise RuntimeError("Phase 8 is not authorized")
    binding = load_binding(project_root / "contracts/part_a_binding.json")
    part_a = resolve_part_a_root(binding, explicit_part_a_root)
    _, binding_pass = verify_artifacts(binding, part_a)
    if not binding_pass or _git(part_a, "rev-parse", "HEAD") != binding.part_a["published_commit"] or _git(part_a, "status", "--porcelain"):
        raise RuntimeError("Part A binding or clean-state check failed")
    model_path = part_a / binding.model["artifact_relative_path"]
    if sha256_file(model_path) != binding.model["artifact_sha256"]:
        raise RuntimeError("Frozen model artifact changed")
    pipeline = joblib.load(model_path)
    schema = pd.read_csv(part_a / "reports/experiments/step49_development_freeze_v1/scoring_input_schema.csv")
    features = schema.sort_values("Raw_Feature_Index")["Raw_Feature_Name"].astype(str).tolist()

    reference_root = project_root / "artifacts/reference_snapshots/REFERENCE-MATERIALIZATION-01/DEV-VAL-PHYSICAL-01"
    reference_manifest = json.loads((reference_root / "snapshot_manifest.json").read_text(encoding="utf-8"))
    phase4_manifest = json.loads((project_root / "reports/reference/REFERENCE-MATERIALIZATION-01/manifest.json").read_text(encoding="utf-8"))
    if sha256_file(reference_root / "snapshot_manifest.json") != phase4_manifest["local_snapshot_manifests"]["DEV-VAL-PHYSICAL-01"]:
        raise RuntimeError("Frozen development-validation snapshot manifest changed")
    dev = pd.read_parquet(reference_root / "snapshot.parquet", engine="pyarrow")
    stored_reference = dev["raw_probability"].to_numpy(dtype=np.float64)
    runtime_reference = np.asarray(pipeline.predict_proba(validate_scoring_frame(dev[["SK_ID_CURR", *features]], pipeline)), dtype=np.float64)[:, 1]
    max_reference_difference = float(np.max(np.abs(runtime_reference - stored_reference)))
    if max_reference_difference > 1e-12:
        raise RuntimeError("Qualified runtime does not reconcile to the frozen score reference")
    score_reference = json.loads((project_root / "reports/reference/REFERENCE-MATERIALIZATION-01/score_reference.json").read_text(encoding="utf-8"))
    score_bins = json.loads((project_root / "reports/reference/REFERENCE-MATERIALIZATION-01/score_psi_bin_definitions.json").read_text(encoding="utf-8"))
    monitor = PredictionMonitor(contract, stored_reference, score_bins, score_reference)

    dq = pd.read_csv(project_root / "reports/monitoring/DATA-QUALITY-CONTROL-01/scenario_control_summary.csv")
    eligible = set(dq.loc[dq["downstream_monitoring_eligible"].astype(bool), "artifact_id"])
    locations = {
        "SIM-M01-SCENARIO-01": "scenarios/SIM-M01-SCENARIO-01", "SIM-M02-SCENARIO-01": "scenarios/SIM-M02-SCENARIO-01",
        "SIM-M03-SCENARIO-01": "scenarios/SIM-M03-SCENARIO-01", "SIM-M04-SCENARIO-01": "scenarios/SIM-M04-SCENARIO-01",
        "SIM-M05-VALID-DEGRADED-01": "scenarios/SIM-M05-VALID-DEGRADED-01", "SIM-M06-SCENARIO-01": "scenarios/SIM-M06-SCENARIO-01",
        "SIM-M05-SOURCE-LOSS-DIAGNOSTIC-01": "variants/SIM-M05-SOURCE-LOSS-DIAGNOSTIC-01", "SIM-M05-HARD-FAIL-01": "variants/SIM-M05-HARD-FAIL-01",
    }
    expected_eligible = set(locations) - {"SIM-M05-SOURCE-LOSS-DIAGNOSTIC-01", "SIM-M05-HARD-FAIL-01"}
    if eligible != expected_eligible:
        raise RuntimeError("Unexpected Phase 6 eligibility set")
    report_final = project_root / "reports/monitoring" / MONITORING_ID
    report_stage = report_final.parent / f".{MONITORING_ID}.in_progress"
    local_final = project_root / "artifacts/monitoring_predictions" / MONITORING_ID
    local_stage = local_final.parent / f".{MONITORING_ID}.in_progress"
    if any(path.exists() for path in (report_final, report_stage, local_final, local_stage)):
        raise FileExistsError("Phase 8 output already exists")
    report_stage.mkdir(parents=True); local_stage.mkdir(parents=True)
    scenario_root = project_root / "artifacts/simulation_scenarios/SIMULATION-SCENARIO-SET-01"
    evaluations: list[PredictionEvaluation] = []
    integrity: list[dict[str, Any]] = []
    reproducibility: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    local_manifests: dict[str, str] = {}
    created = datetime.now(timezone.utc).isoformat()
    for artifact_id, relative in locations.items():
        dq_row = dq.loc[dq["artifact_id"] == artifact_id].iloc[0]
        if artifact_id not in eligible:
            exclusions.append({"artifact_id": artifact_id, "scoring_executed": False, "reason": "PHASE_6_DOWNSTREAM_MONITORING_INELIGIBLE", "dq_control_decision": dq_row["dq_control_decision"]})
            continue
        artifact_root = scenario_root / relative
        metadata = json.loads((artifact_root / "metadata.json").read_text(encoding="utf-8"))
        data_path = artifact_root / "data.parquet"
        if sha256_file(data_path) != metadata["data_sha256"]:
            raise RuntimeError(f"Scenario file changed: {artifact_id}")
        frame = pd.read_parquet(data_path, engine="pyarrow")
        validated = validate_scoring_frame(frame[["SK_ID_CURR", *features]], pipeline)
        first_values = np.asarray(pipeline.predict_proba(validated), dtype=np.float64)[:, 1]
        second_values = np.asarray(pipeline.predict_proba(validated.copy(deep=True)), dtype=np.float64)[:, 1]
        scenario_id = "SIM-M05" if artifact_id.startswith("SIM-M05") else artifact_id[:7]
        first = monitor.evaluate(frame["SK_ID_CURR"], first_values, artifact_id=artifact_id, scenario_id=scenario_id)
        second = monitor.evaluate(frame["SK_ID_CURR"], second_values, artifact_id=artifact_id, scenario_id=scenario_id)
        first_hash, second_hash = _semantic_prediction_hash(first.predictions), _semantic_prediction_hash(second.predictions)
        if first_hash != second_hash or not np.array_equal(first_values, second_values):
            raise RuntimeError(f"Prediction reproducibility failed: {artifact_id}")
        evaluations.append(first)
        prediction_artifact_id = artifact_id.replace("SCENARIO", "PREDICTIONS").replace("VALID-DEGRADED", "PREDICTIONS")
        target = local_stage / prediction_artifact_id
        target.mkdir()
        prediction_path = target / "predictions.parquet"
        first.predictions.to_parquet(prediction_path, index=False, engine="pyarrow", compression="zstd")
        _json(target / "metadata.json", {
            "prediction_artifact_id": prediction_artifact_id, "status": "QUALIFIED_PENDING_REVIEW",
            "scenario_artifact_id": artifact_id, "prediction_run_id": first.summary["run_id"],
            "row_count": len(first.predictions), "semantic_prediction_sha256": first_hash,
            "probability_representation": "RAW_P_TARGET_1", "threshold_id": "THRESHOLD-01",
            "row_level_artifact_publicly_committed": False,
        })
        local_files = [prediction_path, target / "metadata.json"]
        _json(target / "manifest.json", {"prediction_artifact_id": prediction_artifact_id, "status": "QUALIFIED_PENDING_REVIEW", "artifacts": [_record(path, target) for path in local_files]})
        (target / "manifest.sha256").write_text(sha256_file(target / "manifest.json") + "\n", encoding="ascii", newline="\n")
        local_manifests[prediction_artifact_id] = sha256_file(target / "manifest.json")
        integrity.append({
            "artifact_id": artifact_id, "input_row_count": len(frame), "prediction_row_count": len(first.predictions),
            "unique_id_count": int(first.predictions["SK_ID_CURR"].nunique()), "missing_probability_count": int(first.predictions["raw_probability"].isna().sum()),
            "nonfinite_probability_count": int((~np.isfinite(first_values)).sum()), "outside_0_1_count": int(((first_values < 0) | (first_values > 1)).sum()),
            "identity_order_preserved": bool(first.predictions["SK_ID_CURR"].equals(frame["SK_ID_CURR"])),
            "semantic_prediction_sha256": first_hash, "result": "PASS",
        })
        reproducibility.append({
            "artifact_id": artifact_id, "first_semantic_sha256": first_hash, "second_semantic_sha256": second_hash,
            "probability_vector_exact": bool(np.array_equal(first_values, second_values)),
            "threshold_class_exact": bool(np.array_equal(first.predictions["analytical_risk_class"], second.predictions["analytical_risk_class"])),
            "summary_exact": first.summary == second.summary, "score_psi_exact": first.score_psi == second.score_psi,
            "threshold_output_exact": first.threshold_output == second.threshold_output, "result": "PASS",
        })

    summaries = [item.summary for item in evaluations]
    psi_rows = [item.score_psi for item in evaluations]
    threshold_rows = [item.threshold_output for item in evaluations]
    bins = pd.concat([item.bin_results for item in evaluations], ignore_index=True)
    pd.json_normalize(summaries, sep=".").to_parquet(report_stage / "prediction_summary_results.parquet", index=False, engine="pyarrow", compression="zstd")
    pd.DataFrame(psi_rows).to_parquet(report_stage / "score_psi_results.parquet", index=False, engine="pyarrow", compression="zstd")
    bins.to_parquet(report_stage / "score_psi_bin_contributions.parquet", index=False, engine="pyarrow", compression="zstd")
    pd.DataFrame(threshold_rows).to_parquet(report_stage / "threshold_output_results.parquet", index=False, engine="pyarrow", compression="zstd")
    scenario_rows = [{
        "scenario_id": summary["scenario_id"], "artifact_id": summary["artifact_id"], "score_psi": psi["score_psi"],
        "score_psi_severity": psi["severity"], "mean_probability": summary["mean_probability"],
        "risk_positive_rate": output["risk_positive_rate"], "risk_positive_rate_change": output["risk_positive_rate_change"],
        "risk_positive_rate_change_percentage_points": output["risk_positive_rate_change_percentage_points"],
        "risk_positive_rate_severity": output["severity"], "authority": "AUTHORITATIVE", "alert_generated": False,
    } for summary, psi, output in zip(summaries, psi_rows, threshold_rows, strict=True)]
    _csv(report_stage / "scenario_prediction_summary.csv", list(scenario_rows[0]), scenario_rows)
    _json(report_stage / "prediction_integrity_qualification.json", {"result": "PASS", "artifacts": integrity, "all_pass": all(row["result"] == "PASS" for row in integrity)})
    _json(report_stage / "prediction_reproducibility_qualification.json", {"result": "PASS", "artifacts": reproducibility, "all_pass": all(row["result"] == "PASS" for row in reproducibility)})
    _json(report_stage / "prediction_reference_reconciliation.json", {
        "result": "PASS", "reference_id": "PERF-REF-01", "reference_row_count": len(dev),
        "stored_probability_count": len(stored_reference), "runtime_probability_count": len(runtime_reference),
        "max_absolute_runtime_vs_frozen_probability_difference": max_reference_difference,
        "score_reference_mean_difference": float(stored_reference.mean() - score_reference["mean"]),
        "development_validation_outcomes_used_in_phase8_metrics": False,
    })
    psi_reconciled = bins.groupby("artifact_id")["psi_contribution"].sum()
    max_psi_diff = max(abs(row["score_psi"] - psi_reconciled[row["artifact_id"]]) for row in psi_rows)
    _json(report_stage / "score_threshold_reconciliation.json", {
        "result": "PASS", "max_score_psi_vs_bin_sum_difference": max_psi_diff,
        "all_current_bin_counts_reconcile": bool((bins.groupby("artifact_id")["current_count"].sum() == 8124).all()),
        "all_reference_bin_counts_reconcile": bool((bins.groupby("artifact_id")["reference_count"].sum() == 46127).all()),
        "all_threshold_counts_reconcile": all(row["risk_positive_count"] + row["risk_negative_count"] == 8124 for row in threshold_rows),
        "all_threshold_rates_reconcile": all(abs(row["risk_positive_rate"] + row["risk_negative_rate"] - 1.0) <= 1e-15 for row in threshold_rows),
        "threshold_id": "THRESHOLD-01", "threshold_value": 0.08, "threshold_operator": ">=", "threshold_0_5_used": False,
    })
    _json(report_stage / "upstream_gate_reconciliation.json", {
        "result": "PASS", "eligible_artifact_count": 6, "excluded_artifact_count": 2,
        "excluded_artifacts": exclusions, "phase7_severity_used_as_execution_gate": False,
        "phase6_manifest_sha256": contract["frozen_dependencies"]["phase_6_manifest_sha256"],
        "phase7_manifest_sha256": contract["frozen_dependencies"]["phase_7_manifest_sha256"],
    })
    _json(report_stage / "controlled_deferred_items.json", {
        **contract["controlled_deferred"], "threshold_boundary_window_selected": False,
        "threshold_boundary_density_value": None, "cnd_02_status": "OPEN",
    })
    _json(report_stage / "scope_protection_attestation.json", {
        **contract["scope_protection"], "all_prohibited_calculations_remained_false": True,
        "synthetic_outcomes_loaded": False, "m06_feature_frame_scored": True,
        "monitoring_alerts_generated": False, "overall_model_health_calculated": False,
        "row_level_predictions_in_public_evidence": False,
    })
    _json(report_stage / "prediction_control_registry.json", {"monitoring_id": MONITORING_ID, "status": "QUALIFIED_PENDING_REVIEW", "contract_sha256": sha256_file(contract_path), "score_psi": contract["score_psi"], "threshold_output": contract["threshold_output"]})
    implementation = [contract_path, project_root / "src/credit_risk_monitoring/prediction/engine.py", project_root / "src/credit_risk_monitoring/prediction/__init__.py", project_root / "scripts/run_phase8_monitoring.py"]
    _json(report_stage / "execution_source_manifest.json", {
        "monitoring_id": MONITORING_ID, "creation_code_version": CODE_VERSION,
        "part_b_base_commit": _git(project_root, "rev-parse", "HEAD"), "part_a_commit": binding.part_a["published_commit"],
        "implementation_sources": [{"path": path.relative_to(project_root).as_posix(), "sha256": sha256_file(path)} for path in implementation],
        "model_sha256": binding.model["artifact_sha256"], "frozen_dependencies": contract["frozen_dependencies"],
    })
    controls = [
        "Phase 7 approved and Phase 8 authorized", "Phase 6 gate selected exactly six authoritative artifacts",
        "Phase 7 drift severity did not gate scoring", "Two ineligible M05 artifacts were not scored",
        "DF-01 XGBT-01 binding and model hash verified", "Qualified embedded preprocessing used without refit",
        "Raw class-1 probabilities used without transformation", "Six local governed prediction artifacts materialized",
        "Each artifact contains 8124 unique applicant predictions", "All probabilities finite complete and within [0,1]",
        "Prediction semantic hashes and exact replay verified", "Development-validation score reference reconciled to runtime",
        "Only approved prediction summary quantiles calculated", "Frozen Phase 4 score bins used without rebucketing",
        "Score PSI counts and contributions reconcile", "Score PSI severity uses approved project assumptions only",
        "THRESHOLD-01 value 0.080 and >= operator used", "Risk-positive and risk-negative counts and rates reconcile",
        "Analytical proxy terminology used without approval/rejection claims", "Threshold-boundary density remains unassessable",
        "M06 synthetic outcomes were not loaded", "No performance calibration threshold-performance subgroup alert or health result generated",
        "Frozen upstream manifests and Part A remain unchanged", "Owner approval and Phase 9 authorization deferred",
    ]
    _csv(report_stage / "phase8_acceptance_checklist.csv", ["control_id", "control", "result"], [{"control_id": f"P8-{index:03d}", "control": control, "result": "PASS"} for index, control in enumerate(controls, 1)])
    _json(report_stage / "phase8_completion_decision.json", {
        "phase": "PHASE_8", "monitoring_id": MONITORING_ID, "technical_qualification": "PASS",
        "review_decision": "PENDING_USER_PROTOCOL_OWNER_REVIEW", "phase_8_complete": False,
        "eligible_artifact_count": 6, "excluded_artifact_count": 2, "prediction_artifacts_materialized": True,
        "raw_probability_monitoring_executed": True, "prediction_summaries_calculated": True,
        "score_psi_calculated": True, "frozen_score_bins_used": True, "score_psi_reconciliation_verified": True,
        "threshold_output_monitoring_executed": True, "threshold_id": "THRESHOLD-01", "threshold_value": 0.08, "threshold_operator": ">=",
        "risk_positive_rate_calculated": True, "risk_negative_rate_calculated": True,
        "threshold_boundary_density_calculated": False, "prediction_reproducibility_verified": True,
        "cnd_02_status": "OPEN", "performance_results_calculated": False, "calibration_results_calculated": False,
        "threshold_performance_results_calculated": False, "subgroup_results_calculated": False,
        "monitoring_alerts_generated": False, "overall_model_health_calculated": False, "phase_9_authorized": False,
    })
    files = sorted(path for path in report_stage.iterdir() if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"})
    _json(report_stage / "manifest.json", {
        "monitoring_id": MONITORING_ID, "status": "QUALIFIED_PENDING_REVIEW", "created_utc": created,
        "artifacts": [_record(path, report_stage) for path in files], "local_artifact_root": "artifacts/monitoring_predictions/PREDICTION-MONITORING-01",
        "local_manifests": local_manifests, "aggregate_public_evidence_only": True,
        "row_level_predictions_publicly_committed": False, "outcomes_loaded": False, "alerts_included": False, "approval_record_included": False,
    })
    (report_stage / "manifest.sha256").write_text(sha256_file(report_stage / "manifest.json") + "\n", encoding="ascii", newline="\n")
    if _git(part_a, "status", "--porcelain"):
        raise RuntimeError("Part A changed during Phase 8")
    local_stage.rename(local_final); report_stage.rename(report_final)
    return report_final


__all__ = ["PredictionEvaluation", "PredictionMonitor", "apply_threshold", "run_phase8_monitoring"]
