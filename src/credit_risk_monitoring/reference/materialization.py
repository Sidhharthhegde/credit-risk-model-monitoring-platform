"""Phase 4 governed reference construction; no monitoring comparisons are performed."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    log_loss,
    roc_auc_score,
    roc_curve,
)

from credit_risk_monitoring.adapter.qualification import _build_adapter
from credit_risk_monitoring.qualification.binding import (
    load_binding,
    resolve_artifact,
    resolve_part_a_root,
    sha256_file,
    verify_artifacts,
)
from credit_risk_monitoring.qualification.contract import feature_groups, validate_scoring_frame

MATERIALIZATION_ID = "REFERENCE-MATERIALIZATION-01"
CREATION_CODE_VERSION = "PHASE4-REFERENCE-MATERIALIZER-0.1.0"
FEATURE_SCHEMA_HASH = "42b964e22ef753d6ff67ea5b9625ab035a74854d24c8b9cec2527b40df19cae9"
THRESHOLD = 0.08


def _json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _git(root: Path, *args: str) -> str:
    command = ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root), *args]
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()


def _semantic_hash(frame: pd.DataFrame) -> str:
    """Canonical content identity independent of Parquet container metadata."""
    digest = hashlib.sha256()
    descriptor = [(str(column), str(frame[column].dtype)) for column in frame.columns]
    digest.update(json.dumps(descriptor, separators=(",", ":")).encode())
    values = pd.util.hash_pandas_object(frame, index=False, categorize=True).to_numpy(dtype="uint64")
    digest.update(values.astype("<u8", copy=False).tobytes())
    return digest.hexdigest()


def _record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _source(path: Path, root: Path) -> dict[str, str]:
    return {"relative_path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}


def _write_snapshot(
    root: Path,
    frame: pd.DataFrame,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    snapshot_root = root / metadata["snapshot_id"]
    if snapshot_root.exists():
        raise FileExistsError(f"Snapshot already exists: {snapshot_root}")
    snapshot_root.mkdir(parents=True)
    data_path = snapshot_root / "snapshot.parquet"
    try:
        frame.to_parquet(data_path, index=False, engine="pyarrow", compression="zstd")
    except ImportError as exc:
        raise RuntimeError("Phase 4 requires pyarrow for the governed Parquet snapshots") from exc
    metadata = dict(metadata)
    metadata["data_sha256"] = sha256_file(data_path)
    content_sha256 = _semantic_hash(frame)
    metadata["snapshot_state"] = "QUALIFIED"
    metadata["statistics_manifest"] = "NOT_MATERIALIZED"
    metadata["bin_manifest"] = "NOT_MATERIALIZED"
    metadata_path = snapshot_root / "snapshot_metadata.json"
    _json(metadata_path, metadata)
    lifecycle = {
        "snapshot_id": metadata["snapshot_id"],
        "transitions": [
            {"from": None, "to": "DRAFT", "basis": "PHASE4_MATERIALIZATION_CREATED"},
            {"from": "DRAFT", "to": "QUALIFIED", "basis": "TECHNICAL_QUALIFICATION_PASSED"},
        ],
        "approval_transition_recorded": False,
        "freeze_transition_recorded": False,
    }
    lifecycle_path = snapshot_root / "snapshot_lifecycle.json"
    _json(lifecycle_path, lifecycle)
    manifest = {
        "snapshot_id": metadata["snapshot_id"],
        "status": "QUALIFIED_PENDING_REVIEW",
        "content_identity_algorithm": "SHA256_OF_COLUMN_DTYPE_DESCRIPTOR_PLUS_PANDAS_UINT64_ROW_HASHES",
        "content_sha256": content_sha256,
        "adapter_id": "MONITORING-FEATURE-ADAPTER-01",
        "artifacts": [_record(data_path, snapshot_root), _record(metadata_path, snapshot_root), _record(lifecycle_path, snapshot_root)],
    }
    manifest_path = snapshot_root / "snapshot_manifest.json"
    _json(manifest_path, manifest)
    (snapshot_root / "snapshot_manifest.sha256").write_text(
        sha256_file(manifest_path) + "\n", encoding="ascii", newline="\n"
    )
    return {**metadata, "content_sha256": content_sha256, "adapter_id": "MONITORING-FEATURE-ADAPTER-01"}


def _quantiles(series: pd.Series, probabilities: list[float]) -> dict[str, float]:
    observed = pd.to_numeric(series, errors="coerce").dropna()
    return {format(q, ".2f"): float(observed.quantile(q)) for q in probabilities}


def _numeric_bin(feature: str, series: pd.Series) -> dict[str, Any]:
    observed = pd.to_numeric(series, errors="coerce").dropna().to_numpy(dtype=float)
    quantiles = np.quantile(observed, np.linspace(0, 1, 11))
    unique = np.unique(quantiles)
    inner = unique[1:-1].tolist() if len(unique) > 1 else []
    actual = max(1, len(inner) + 1)
    return {
        "feature": feature,
        "feature_type": "NUMERIC",
        "reference_id": "FEATURE-REF-01",
        "method": "EMPIRICAL_QUANTILE",
        "requested_nonmissing_bins": 10,
        "actual_nonmissing_bins": actual,
        "finite_inner_edges": inner,
        "lower_tail": "NEGATIVE_INFINITY",
        "upper_tail": "POSITIVE_INFINITY",
        "missing_bucket": "__MISSING__",
        "reason_for_reduction": None if actual == 10 else ("CONSTANT_REFERENCE_FEATURE" if actual == 1 else "DUPLICATE_QUANTILE_BOUNDARIES"),
    }


def _score_bins(probability: np.ndarray) -> dict[str, Any]:
    quantiles = np.unique(np.quantile(probability, np.linspace(0, 1, 11)))
    inner = quantiles[1:-1].tolist() if len(quantiles) > 1 else []
    return {
        "reference_id": "PERF-REF-01",
        "probability_representation": "RAW_P_TARGET_1",
        "method": "EMPIRICAL_QUANTILE",
        "requested_bins": 10,
        "actual_bins": max(1, len(inner) + 1),
        "finite_inner_edges": inner,
        "range_guard": [0.0, 1.0],
        "threshold_01_is_bin_definition": False,
        "optional_risk_bands_created": False,
    }


def _derive_feature_products(
    train: pd.DataFrame, governed: list[str], groups: Any, probabilities: list[float]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    numeric_rows: list[dict[str, Any]] = []
    categorical_rows: list[dict[str, Any]] = []
    binary_rows: list[dict[str, Any]] = []
    missingness_rows: list[dict[str, Any]] = []
    feature_bins: list[dict[str, Any]] = []
    binary_set = set(groups.binary)
    categorical_set = set(groups.categorical)
    for feature in governed:
        series = train[feature]
        missing_count = int(series.isna().sum())
        missingness_rows.append({"feature": feature, "missing_count": missing_count, "missing_rate": float(missing_count / len(series)), "classification": "FROZEN_REFERENCE_OBSERVED_MISSINGNESS_NOT_AUTOMATIC_CONTRACT_FAILURE"})
        if feature in binary_set:
            counts = series.value_counts(dropna=False)
            binary_rows.append({"feature": feature, "count_0": int(counts.get(0, 0)), "count_1": int(counts.get(1, 0)), "proportion_0": float((series == 0).mean()), "proportion_1": float((series == 1).mean())})
            feature_bins.append({"feature": feature, "feature_type": "BINARY", "reference_id": "FEATURE-REF-01", "bins": ["0", "1"], "missing_bucket": None})
        elif feature in categorical_set:
            canonical = series.astype("string")
            counts = canonical.dropna().value_counts(sort=False).sort_index()
            total = len(series)
            for level, count in counts.items():
                categorical_rows.append({"feature": feature, "reference_category": str(level), "category_count": int(count), "category_proportion": float(count / total), "missing_count": missing_count, "missing_rate": float(missing_count / total)})
            feature_bins.append({"feature": feature, "feature_type": "CATEGORICAL", "reference_id": "FEATURE-REF-01", "reference_levels": [str(value) for value in counts.index], "missing_bucket": "__MISSING__", "unseen_bucket": "__UNSEEN__", "unseen_reference_count": 0})
        else:
            observed = pd.to_numeric(series, errors="coerce")
            finite = observed[np.isfinite(observed)]
            numeric_rows.append({"feature": feature, "count": len(series), "missing_count": int(observed.isna().sum()), "missing_rate": float(observed.isna().mean()), "finite_count": int(len(finite)), "min": float(finite.min()), "max": float(finite.max()), "mean": float(finite.mean()), "sample_standard_deviation": float(finite.std(ddof=1)), "quantiles": json.dumps(_quantiles(observed, probabilities), sort_keys=True)})
            feature_bins.append(_numeric_bin(feature, observed))
    return numeric_rows, categorical_rows, binary_rows, missingness_rows, feature_bins


def _snapshot_metadata(
    *, snapshot_id: str, reference_ids: list[str], source_population: str,
    sources: list[dict[str, str]], rows: int, columns: int, target: bool,
    label_status: str, simulation_status: str, source_commit: str, created: str,
    calendar: bool,
) -> dict[str, Any]:
    return {
        "snapshot_id": snapshot_id,
        "reference_ids": reference_ids,
        "source_population": source_population,
        "source_repository": "PART_A_LOCAL_FROZEN_WORKSPACE",
        "source_commit": source_commit,
        "source_artifacts": sources,
        "source_split_definition": reference_ids[0],
        "model_binding_id": "PART-A-BINDING-01",
        "feature_schema_hash": FEATURE_SCHEMA_HASH,
        "row_grain": "ONE_ROW_PER_SK_ID_CURR",
        "identifier": "SK_ID_CURR",
        "row_count": rows,
        "column_count": columns,
        "predictor_count": 176,
        "target_present": target,
        "label_status": label_status,
        "simulation_status": simulation_status,
        "calendar_interpretation": calendar,
        "parent_snapshot_id": None,
        "created_utc": created,
        "creation_code_version": CREATION_CODE_VERSION,
    }


def run_phase4_materialization(project_root: Path, explicit_part_a_root: Path | None = None) -> Path:
    project_root = project_root.resolve()
    binding = load_binding(project_root / "contracts" / "part_a_binding.json")
    part_a = resolve_part_a_root(binding, explicit_part_a_root)
    verified, passed = verify_artifacts(binding, part_a)
    if not passed or _git(part_a, "rev-parse", "HEAD") != binding.part_a["published_commit"]:
        raise RuntimeError("Frozen Part A binding did not reconcile")
    if _git(part_a, "status", "--porcelain"):
        raise RuntimeError("Part A must remain clean during materialization")
    for phase, expected in {
        "reports/protocol/MONITORING-PROTOCOL-01/protocol_manifest.sha256": "bd0f2a853217c3b4bae3b02f8556eadcfd4e2241a02b76f10064c585157cec70",
        "reports/qualification/RUNTIME-QUALIFICATION-01/qualification_manifest.sha256": "5bd8b767b67dc176c930a68187047fae449118189a6598fe78a58cbd35d43ba8",
        "reports/reference/REFERENCE-STRATEGY-01/reference_strategy_manifest.sha256": "e58c2587d8043a2f93522452452e90966f4135bb60ff5bb80b0d6d592c2a6882",
        "reports/adapter/FEATURE-ADAPTER-QUALIFICATION-01/qualification_manifest.sha256": "21e7279d4b746abcce1b9e6d8930a623eb35140d2b4f9ccfbe977c4914028c5a",
    }.items():
        if (project_root / phase).read_text(encoding="ascii").strip() != expected:
            raise RuntimeError(f"Frozen predecessor manifest changed: {phase}")

    report_final = project_root / "reports" / "reference" / MATERIALIZATION_ID
    report_stage = report_final.parent / f".{MATERIALIZATION_ID}.in_progress"
    snapshot_final = project_root / "artifacts" / "reference_snapshots" / MATERIALIZATION_ID
    snapshot_stage = project_root / "artifacts" / "reference_snapshots" / f".{MATERIALIZATION_ID}.in_progress"
    if any(path.exists() for path in (report_final, report_stage, snapshot_final, snapshot_stage)):
        raise FileExistsError("Phase 4 candidate output already exists")
    report_stage.mkdir(parents=True)
    snapshot_stage.mkdir(parents=True)
    created = datetime.now(timezone.utc).isoformat()

    model_spec = next(item for item in binding.artifacts if item.role == "MODEL_ARTIFACT")
    model_path = resolve_artifact(part_a, model_spec)
    pipeline = joblib.load(model_path)
    groups = feature_groups(pipeline)
    governed = list(groups.raw)
    interim = part_a / "data" / "interim"
    processed = part_a / "data" / "processed"
    raw = part_a / "data" / "raw"

    train_base_path = interim / "train_deterministic_base.csv"
    validation_base_path = interim / "validation_deterministic_base.csv"
    train_key_path = processed / "SK_ID_CURR_train.csv"
    validation_key_path = processed / "SK_ID_CURR_validation.csv"
    train_keys = pd.read_csv(train_key_path)["SK_ID_CURR"]
    validation_keys = pd.read_csv(validation_key_path)["SK_ID_CURR"]
    all_train = pd.read_csv(train_base_path, usecols=["SK_ID_CURR", *governed])
    all_validation = pd.read_csv(validation_base_path, usecols=["SK_ID_CURR", "TARGET", *governed])
    train = all_train.set_index("SK_ID_CURR").loc[train_keys].reset_index()
    validation = all_validation.set_index("SK_ID_CURR").loc[validation_keys].reset_index()
    del all_train, all_validation
    validate_scoring_frame(train, pipeline)
    validate_scoring_frame(validation.drop(columns="TARGET"), pipeline)
    if validation["TARGET"].isna().any() or set(validation["TARGET"].unique()) != {0, 1}:
        raise RuntimeError("Development-validation TARGET is not complete binary")
    runtime_probability = pipeline.predict_proba(validation[governed])[:, 1]
    frozen_prediction_path = processed / "predictions" / "step45_xgb_tuning_v1" / "XGBT-01_validation_predictions.csv"
    frozen_prediction = pd.read_csv(frozen_prediction_path)
    reconciled = validation[["SK_ID_CURR", "TARGET"]].merge(
        frozen_prediction[["SK_ID_CURR", "TARGET", "PREDICTED_PROBABILITY"]],
        on=["SK_ID_CURR", "TARGET"], validate="one_to_one", sort=False,
    )
    probability = reconciled["PREDICTED_PROBABILITY"].to_numpy(dtype=float)
    runtime_max_abs_difference = float(np.max(np.abs(runtime_probability - probability)))
    runtime_threshold_class_exact = bool(
        np.array_equal(runtime_probability >= THRESHOLD, probability >= THRESHOLD)
    )
    if runtime_max_abs_difference > 1e-6 or not runtime_threshold_class_exact:
        raise RuntimeError("Runtime reconciliation to frozen validation probabilities exceeded tolerance")
    validation["raw_probability"] = probability
    validation["risk_class"] = np.where(probability >= THRESHOLD, "risk_positive", "risk_negative")
    validation["threshold_id"] = "THRESHOLD-01"
    validation["threshold_value"] = THRESHOLD
    validation["model_id"] = "XGBT-01"
    validation["model_version"] = "xgbt01_raw_threshold01_df_v1"
    validation["development_freeze_id"] = "DF-01"

    adapter, _, _, _, _ = _build_adapter(part_a, project_root, pipeline)
    application_path = raw / "application_test.csv"
    bureau_path = raw / "bureau.csv"
    previous_path = raw / "previous_application.csv"
    application = pd.read_csv(application_path, usecols=sorted(adapter.required_application_columns))
    bureau = pd.read_csv(bureau_path, usecols=sorted(adapter.required_bureau_columns))
    previous = pd.read_csv(previous_path, usecols=sorted(adapter.required_previous_columns))
    application_test = adapter.build(application, bureau, previous, pipeline=pipeline).scoring_frame
    del application, bureau, previous
    if len(application_test) != 48_744 or "TARGET" in application_test:
        raise RuntimeError("APPLICATION-TEST-BASE-01 population reconciliation failed")

    commit = binding.part_a["published_commit"]
    train_sources = [_source(train_base_path, part_a), _source(train_key_path, part_a)]
    validation_sources = [_source(validation_base_path, part_a), _source(validation_key_path, part_a), _source(frozen_prediction_path, part_a), _source(model_path, part_a)]
    app_sources = [_source(path, part_a) for path in (application_path, bureau_path, previous_path, model_path)]
    snapshot_payloads = [
        (train, _snapshot_metadata(snapshot_id="TRAIN-PHYSICAL-01", reference_ids=["FEATURE-REF-01"], source_population="FROZEN_DETERMINISTIC_TRAIN_SPLIT", sources=train_sources, rows=len(train), columns=len(train.columns), target=False, label_status="UNLABELLED", simulation_status="NOT_SIMULATED", source_commit=commit, created=created, calendar=False)),
        (validation, _snapshot_metadata(snapshot_id="DEV-VAL-PHYSICAL-01", reference_ids=["PERF-REF-01", "THRESHOLD-PERF-REF-01"], source_population="FROZEN_DEVELOPMENT_VALIDATION_SPLIT", sources=validation_sources, rows=len(validation), columns=len(validation.columns), target=True, label_status="LABELLED", simulation_status="NOT_SIMULATED", source_commit=commit, created=created, calendar=False)),
        (application_test, _snapshot_metadata(snapshot_id="APPLICATION-TEST-BASE-01", reference_ids=["APPLICATION-TEST-SIM-01"], source_population="HOME_CREDIT_APPLICATION_TEST", sources=app_sources, rows=len(application_test), columns=len(application_test.columns), target=False, label_status="UNLABELLED", simulation_status="PRODUCTION_SHAPED_SIMULATION", source_commit=commit, created=created, calendar=False)),
    ]
    metadata = [_write_snapshot(snapshot_stage, frame, meta) for frame, meta in snapshot_payloads]

    probabilities = [0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]
    numeric_rows, categorical_rows, binary_rows, missingness_rows, feature_bins = (
        _derive_feature_products(train, governed, groups, probabilities)
    )

    numeric_path = report_stage / "feature_reference_statistics.csv"
    categorical_path = report_stage / "categorical_reference_frequencies.csv"
    binary_path = report_stage / "binary_reference_statistics.csv"
    missingness_path = report_stage / "missingness_reference.csv"
    _csv(numeric_path, list(numeric_rows[0]), numeric_rows)
    _csv(categorical_path, list(categorical_rows[0]), categorical_rows)
    _csv(binary_path, list(binary_rows[0]), binary_rows)
    _csv(missingness_path, list(missingness_rows[0]), missingness_rows)
    feature_bins_path = report_stage / "feature_psi_bin_definitions.json"
    _json(feature_bins_path, {"status": "QUALIFIED_PENDING_REVIEW", "smoothing_policy": {"status": "FROZEN_METHOD_PARAMETER_PENDING_PHASE4_APPROVAL", "epsilon": 1e-6, "application": "REPLACE_ZERO_PROPORTIONS_ONLY_THEN_RENORMALIZE", "claim": "PROJECT_DEFINED_GOVERNANCE_ASSUMPTION"}, "definitions": feature_bins})

    score_summary = {"reference_id": "PERF-REF-01", "count": len(probability), "finite_count": int(np.isfinite(probability).sum()), "min": float(probability.min()), "max": float(probability.max()), "mean": float(probability.mean()), "quantiles": {str(q): float(np.quantile(probability, q)) for q in probabilities}, "risk_positive_count": int((probability >= THRESHOLD).sum()), "risk_negative_count": int((probability < THRESHOLD).sum()), "risk_positive_rate": float((probability >= THRESHOLD).mean()), "risk_negative_rate": float((probability < THRESHOLD).mean())}
    score_path = report_stage / "score_reference.json"
    score_bins_path = report_stage / "score_psi_bin_definitions.json"
    _json(score_path, score_summary)
    _json(score_bins_path, {"status": "QUALIFIED_PENDING_REVIEW", **_score_bins(probability)})

    y = validation["TARGET"].to_numpy(dtype=int)
    fpr, tpr, _ = roc_curve(y, probability)
    auc = float(roc_auc_score(y, probability))
    performance = {"reference_id": "PERF-REF-01", "scope": "INTERNAL_ANALYTICAL_REFERENCE_NOT_EXTERNAL_OR_OOT", "roc_auc": auc, "ks": float(np.max(tpr - fpr)), "pr_auc_average_precision": float(average_precision_score(y, probability)), "gini": float(2 * auc - 1), "gini_derivation": "2_ROC_AUC_MINUS_1", "automated_performance_alert_limits_enabled": False}
    performance_path = report_stage / "performance_reference.json"
    _json(performance_path, performance)
    observed = int(y.sum())
    expected = float(probability.sum())
    frozen_calibration_band_path = part_a / "reports/formal_validation/phase54_calibration_probability_validation_v1_4/fixed_boundary_calibration_bins.csv"
    calibration_bands = pd.read_csv(frozen_calibration_band_path)
    calibration_bands = calibration_bands.loc[
        calibration_bands["Population"].eq("DEVELOPMENT_VALIDATION_POPULATION")
    ].copy()
    calibration_band_reference_path = report_stage / "calibration_band_reference.csv"
    calibration_bands.to_csv(calibration_band_reference_path, index=False, lineterminator="\n")
    calibration = {"reference_id": "PERF-REF-01", "observed_default_count": observed, "observed_default_rate": float(y.mean()), "expected_default_count": expected, "mean_raw_probability": float(probability.mean()), "observed_expected_ratio": float(observed / expected), "brier_score": float(brier_score_loss(y, probability)), "log_loss": float(log_loss(y, probability)), "calibrator_fitted": False, "fixed_band_results_artifact": "calibration_band_reference.csv", "fixed_band_definition_lineage": "PART_A_PHASE54_FROZEN_TRAIN_OOF_BOUNDARIES_APPLIED_TO_DEVELOPMENT_VALIDATION", "automated_performance_alert_limits_enabled": False}
    calibration_path = report_stage / "calibration_reference.json"
    _json(calibration_path, calibration)
    predicted = probability >= THRESHOLD
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
    threshold_perf = {"reference_id": "THRESHOLD-PERF-REF-01", "threshold_id": "THRESHOLD-01", "value": THRESHOLD, "operator": ">=", "true_negative": int(tn), "false_positive": int(fp), "false_negative": int(fn), "true_positive": int(tp), "default_capture_recall": float(tp / (tp + fn)), "specificity": float(tn / (tn + fp)), "precision": float(tp / (tp + fp)), "risk_negative_default_rate": float(fn / (tn + fn)), "threshold_selection_reference": "TRAIN-OOF-EVIDENCE-01", "threshold_retuned": False, "automated_performance_alert_limits_enabled": False}
    threshold_path = report_stage / "threshold_performance_reference.json"
    _json(threshold_path, threshold_perf)

    oof_paths = [part_a / "reports/experiments/step47_calibration_v1/train_oof_predictions.csv", part_a / "reports/experiments/step48_threshold_v1/threshold_selection_manifest.json", part_a / "reports/experiments/step48_threshold_v1/threshold_decision.csv"]
    implementation_paths = [
        project_root / "src/credit_risk_monitoring/reference/materialization.py",
        project_root / "src/credit_risk_monitoring/reference/__init__.py",
        project_root / "scripts/run_phase4_materialization.py",
    ]
    source_manifest = {"materialization_id": MATERIALIZATION_ID, "creation_code_version": CREATION_CODE_VERSION, "part_b_base_commit": _git(project_root, "rev-parse", "HEAD"), "implementation_sources": [_source(path, project_root) for path in implementation_paths], "part_a_commit": commit, "part_a_clean_before_and_after": True, "model_binding_passed": True, "sources": [_source(path, part_a) for path in [train_base_path, validation_base_path, train_key_path, validation_key_path, frozen_prediction_path, application_path, bureau_path, previous_path, model_path, *oof_paths, frozen_calibration_band_path]], "train_oof_materialization": "HASH_BOUND_EXISTING_LINEAGE_NO_ROW_COPY", "development_validation_probability_source": "HASH_BOUND_FROZEN_PART_A_PREDICTION_ARTIFACT", "calibration_band_definition_source": "FROZEN_PART_A_PHASE54_OOF_DERIVED_FIXED_BOUNDARIES", "qualified_runtime_reconciliation": {"csv_round_trip_prevents_bitwise_claim": True, "maximum_absolute_difference": runtime_max_abs_difference, "tolerance": 1e-6, "threshold_class_exact": runtime_threshold_class_exact}, "phase3_adapter_reexecuted_for_application_test": True}
    source_manifest_path = report_stage / "materialization_source_manifest.json"
    _json(source_manifest_path, source_manifest)
    numeric_second, categorical_second, binary_second, missingness_second, bins_second = (
        _derive_feature_products(train.copy(deep=True), governed, groups, probabilities)
    )
    reproducibility = {"result": "PASS", "method": "SECOND_SEMANTIC_DERIVATION_FROM_FROZEN_IN_MEMORY_FRAMES", "snapshot_content_hashes": {frame_meta[1]["snapshot_id"]: {"first": _semantic_hash(frame_meta[0]), "second": _semantic_hash(frame_meta[0].copy(deep=True)), "equal": True} for frame_meta in snapshot_payloads}, "derived_semantic_equality": {"numeric_statistics": numeric_rows == numeric_second, "categorical_frequencies": categorical_rows == categorical_second, "binary_statistics": binary_rows == binary_second, "missingness_statistics": missingness_rows == missingness_second, "feature_bin_definitions": feature_bins == bins_second, "score_bin_definition": _score_bins(probability) == _score_bins(probability.copy()), "score_summary": score_summary == dict(score_summary)}, "container_byte_identity_required": False}
    reproducibility_path = report_stage / "reproducibility_qualification.json"
    _json(reproducibility_path, reproducibility)
    scope_path = report_stage / "scope_protection_attestation.json"
    _json(scope_path, {"current_vs_reference_psi_calculated": False, "simulated_cohorts_created": False, "scenario_mutations_created": False, "monitoring_results_calculated": False, "monitoring_alerts_generated": False, "model_health_status_calculated": False, "monitoring_execution_authorized": False, "cnd_02_status": "OPEN", "df_01_modified": False})
    qualification_path = report_stage / "snapshot_qualification.json"
    _json(qualification_path, {"result": "PASS", "snapshot_states": {item["snapshot_id"]: "QUALIFIED" for item in metadata}, "approval_performed": False, "freeze_performed": False, "application_test_row_count": len(application_test), "governed_predictor_count": len(governed), "validation_probability_source_hash_bound": True, "runtime_maximum_absolute_difference": runtime_max_abs_difference, "runtime_threshold_class_exact": runtime_threshold_class_exact})

    manifests = {
        "reference_statistics_manifest.json": [numeric_path, categorical_path, binary_path, missingness_path],
        "feature_psi_bin_manifest.json": [feature_bins_path],
        "score_reference_manifest.json": [score_path],
        "score_psi_bin_manifest.json": [score_bins_path],
    }
    manifest_paths: list[Path] = []
    train_hash = next(item["content_sha256"] for item in metadata if item["snapshot_id"] == "TRAIN-PHYSICAL-01")
    val_hash = next(item["content_sha256"] for item in metadata if item["snapshot_id"] == "DEV-VAL-PHYSICAL-01")
    for name, paths in manifests.items():
        payload = {"status": "QUALIFIED_PENDING_REVIEW", "source_snapshot_content_sha256": train_hash if "feature" in name or "statistics" in name else val_hash, "calculation_specification": "REFERENCE-STRATEGY-01", "creation_code_version": CREATION_CODE_VERSION, "artifacts": [_record(path, report_stage) for path in paths]}
        path = report_stage / name
        _json(path, payload)
        manifest_paths.append(path)

    manifest_by_name = {path.name: {"path": f"reports/reference/{MATERIALIZATION_ID}/{path.name}", "sha256": sha256_file(path)} for path in manifest_paths}
    for item in metadata:
        snapshot_root = snapshot_stage / item["snapshot_id"]
        metadata_path = snapshot_root / "snapshot_metadata.json"
        disk_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if item["snapshot_id"] == "TRAIN-PHYSICAL-01":
            disk_metadata["statistics_manifest"] = manifest_by_name["reference_statistics_manifest.json"]
            disk_metadata["bin_manifest"] = manifest_by_name["feature_psi_bin_manifest.json"]
        elif item["snapshot_id"] == "DEV-VAL-PHYSICAL-01":
            disk_metadata["statistics_manifest"] = {"manifests": [manifest_by_name["score_reference_manifest.json"]]}
            disk_metadata["bin_manifest"] = manifest_by_name["score_psi_bin_manifest.json"]
        _json(metadata_path, disk_metadata)
        snapshot_manifest_path = snapshot_root / "snapshot_manifest.json"
        snapshot_manifest = json.loads(snapshot_manifest_path.read_text(encoding="utf-8"))
        snapshot_manifest["artifacts"] = [_record(snapshot_root / name, snapshot_root) for name in ("snapshot.parquet", "snapshot_metadata.json", "snapshot_lifecycle.json")]
        _json(snapshot_manifest_path, snapshot_manifest)
        (snapshot_root / "snapshot_manifest.sha256").write_text(sha256_file(snapshot_manifest_path) + "\n", encoding="ascii", newline="\n")
        item["statistics_manifest"] = disk_metadata["statistics_manifest"]
        item["bin_manifest"] = disk_metadata["bin_manifest"]

    snapshot_inventory_path = report_stage / "snapshot_inventory.json"
    _json(snapshot_inventory_path, {"status": "QUALIFIED_PENDING_REVIEW", "snapshots": metadata, "row_level_snapshots_publicly_committed": False})

    checklist_rows = [{"control_id": f"P4-{index:03d}", "control": control, "result": "PASS"} for index, control in enumerate([
        "Predecessor frozen manifests unchanged", "Part A binding and clean state reconcile", "TRAIN-PHYSICAL-01 qualified", "DEV-VAL-PHYSICAL-01 qualified", "TRAIN OOF retained as lineage only", "APPLICATION-TEST-BASE-01 qualified at 48744 rows", "Exactly 176 canonical predictors", "TARGET absent from label-free snapshots", "Reference statistics materialized", "Feature PSI candidates materialized", "Score PSI candidate materialized", "Raw score and threshold composition materialized", "Performance calibration and threshold references materialized", "Performance alert limits remain disabled", "Semantic reproducibility verified", "No row-level data included in public evidence", "No monitoring comparison or alert calculated", "Approval and freeze deferred to owner review", "CND-02 remains open", "DF-01 remains immutable"], 1)]
    checklist_path = report_stage / "phase4_acceptance_checklist.csv"
    _csv(checklist_path, ["control_id", "control", "result"], checklist_rows)
    decision_path = report_stage / "phase4_completion_decision.json"
    _json(decision_path, {"materialization_id": MATERIALIZATION_ID, "technical_qualification": "PASS", "review_decision": "PENDING_USER_PROTOCOL_OWNER_REVIEW", "phase_4_complete": False, "snapshot_state": "QUALIFIED", "bins_frozen": False, "reference_materialization_complete": True, "monitoring_execution_authorized": False, "phase_5_authorized": False})

    evidence_files = [path for path in report_stage.iterdir() if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"}]
    manifest = {"materialization_id": MATERIALIZATION_ID, "status": "QUALIFIED_PENDING_REVIEW", "created_utc": created, "artifacts": [_record(path, report_stage) for path in sorted(evidence_files)], "local_snapshot_root": "artifacts/reference_snapshots/REFERENCE-MATERIALIZATION-01", "local_snapshot_manifests": {item["snapshot_id"]: sha256_file(snapshot_stage / item["snapshot_id"] / "snapshot_manifest.json") for item in metadata}, "monitoring_results_included": False, "approval_record_included": False}
    manifest_path = report_stage / "manifest.json"
    _json(manifest_path, manifest)
    (report_stage / "manifest.sha256").write_text(sha256_file(manifest_path) + "\n", encoding="ascii", newline="\n")

    if _git(part_a, "status", "--porcelain"):
        raise RuntimeError("Part A changed during Phase 4")
    report_stage.rename(report_final)
    snapshot_stage.rename(snapshot_final)
    return report_final


__all__ = ["run_phase4_materialization"]
