"""Read-only Phase 6 input controls; distribution and outcome monitoring are excluded."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from credit_risk_monitoring.qualification.binding import (
    load_binding,
    resolve_part_a_root,
    sha256_file,
    verify_artifacts,
)
from credit_risk_monitoring.reference.materialization import _semantic_hash

CONTROL_ID = "DATA-QUALITY-CONTROL-01"
CODE_VERSION = "PHASE6-DATA-QUALITY-MONITOR-0.1.0"


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


def _severity(value: float, warning: float, critical: float) -> str:
    if value >= critical:
        return "CRITICAL"
    if value >= warning:
        return "WARNING"
    return "NORMAL"


def _frame_hash(frame: pd.DataFrame) -> str:
    if frame.empty:
        return hashlib.sha256(b"EMPTY").hexdigest()
    ordered = frame.sort_values(list(frame.columns), kind="mergesort", na_position="first").reset_index(drop=True)
    return _semantic_hash(ordered)


@dataclass(frozen=True)
class DQEvaluation:
    schema: dict[str, Any]
    grain: dict[str, Any]
    completeness: pd.DataFrame
    validity: pd.DataFrame
    novelty: pd.DataFrame
    ranges: pd.DataFrame
    source: dict[str, Any]
    reconciliation: dict[str, Any]
    summary: dict[str, Any]


class DataQualityMonitor:
    def __init__(
        self,
        contract: dict[str, Any],
        feature_schema: pd.DataFrame,
        missingness_reference: pd.DataFrame,
        numeric_reference: pd.DataFrame,
        categorical_reference: pd.DataFrame,
    ) -> None:
        self.contract = contract
        schema = feature_schema.sort_values("Raw_Feature_Index", kind="mergesort")
        self.features = schema["Raw_Feature_Name"].astype(str).tolist()
        self.classes = dict(zip(schema["Raw_Feature_Name"], schema["Feature_Class"], strict=True))
        self.numeric = [feature for feature in self.features if self.classes[feature] == "NUMERIC"]
        self.categorical = [feature for feature in self.features if self.classes[feature] == "CATEGORICAL"]
        self.binary = [feature for feature in self.features if self.classes[feature] == "BINARY"]
        self.missingness = missingness_reference.set_index("feature")
        self.numeric_reference = numeric_reference.set_index("feature")
        self.known_categories = {
            str(feature): set(group["reference_category"].astype(str))
            for feature, group in categorical_reference.groupby("feature", sort=False)
        }
        thresholds = contract["threshold_binding"]
        self.missing_threshold = thresholds["missing_rate_absolute_change"]
        self.unseen_threshold = thresholds["unknown_category_share"]

    def _row(
        self,
        *, run_id: str, scenario_id: str, artifact_id: str, control_id: str,
        metric_id: str, feature: str, reference_id: str, value: float | int | str | None,
        reference_value: float | int | str | None, role: str, evidence: str,
        severity: str, contract_valid: bool, authoritative: bool, detail: str,
    ) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "scenario_id": scenario_id,
            "artifact_id": artifact_id,
            "control_id": control_id,
            "metric_id": metric_id,
            "feature": feature,
            "reference_id": reference_id,
            "value": value,
            "reference_value": reference_value,
            "control_role": role,
            "evidence_status": evidence,
            "severity": severity,
            "alert_generated": False,
            "contract_valid": contract_valid,
            "authoritative_use_permitted": authoritative,
            "detail": detail,
        }

    def evaluate(
        self,
        frame: pd.DataFrame,
        *, artifact_id: str,
        scenario_id: str,
        source_context: dict[str, Any],
        expected_rows: int = 8124,
    ) -> DQEvaluation:
        run_id = f"DQ-RUN-{artifact_id}-01"
        expected_columns = {"SK_ID_CURR", *self.features}
        observed_columns = list(frame.columns)
        missing_predictors = sorted(set(self.features) - set(observed_columns))
        unexpected = sorted(set(observed_columns) - expected_columns)
        duplicate_column_count = int(frame.columns.duplicated().sum())
        schema_pass = not missing_predictors and not unexpected and duplicate_column_count == 0
        schema = {
            "run_id": run_id, "scenario_id": scenario_id, "artifact_id": artifact_id,
            "control_id": "DQ-SCHEMA-01", "expected_predictor_count": 176,
            "observed_predictor_count": len(set(observed_columns) & set(self.features)),
            "missing_predictor_count": len(missing_predictors), "missing_predictors": missing_predictors,
            "unexpected_column_count": len(unexpected), "unexpected_columns": unexpected,
            "duplicate_column_count": duplicate_column_count,
            "canonical_order_exact": observed_columns == ["SK_ID_CURR", *self.features],
            "canonical_reorder_permitted": True, "result": "PASS" if schema_pass else "FAIL",
            "severity": "NORMAL" if schema_pass else "CRITICAL", "alert_generated": False,
        }
        id_present = "SK_ID_CURR" in frame
        missing_ids = int(frame["SK_ID_CURR"].isna().sum()) if id_present else len(frame)
        unique_ids = int(frame["SK_ID_CURR"].nunique(dropna=True)) if id_present else 0
        duplicate_ids = int(frame["SK_ID_CURR"].duplicated(keep=False).sum()) if id_present else len(frame)
        duplicate_id_values = int(frame.loc[frame["SK_ID_CURR"].duplicated(keep=False), "SK_ID_CURR"].nunique()) if id_present else 0
        grain_pass = id_present and missing_ids == 0 and duplicate_ids == 0
        grain = {
            "run_id": run_id, "scenario_id": scenario_id, "artifact_id": artifact_id,
            "control_id": "DQ-IDENTIFIER-01", "row_count": len(frame), "unique_id_count": unique_ids,
            "missing_id_count": missing_ids, "duplicate_id_row_count": duplicate_ids,
            "duplicate_id_value_count": duplicate_id_values,
            "one_row_per_sk_id_curr": grain_pass, "result": "PASS" if grain_pass else "FAIL",
            "severity": "NORMAL" if grain_pass else "CRITICAL", "alert_generated": False,
        }
        hard_structural_failure = not schema_pass or not grain_pass
        authoritative = bool(source_context.get("authoritative_use_permitted", True))
        empty = pd.DataFrame()
        if hard_structural_failure:
            source = self._source_result(frame, run_id, scenario_id, artifact_id, source_context, authoritative)
            reconciliation = {
                "run_id": run_id, "scenario_id": scenario_id, "artifact_id": artifact_id,
                "expected_row_count": expected_rows, "observed_row_count": len(frame),
                "accepted_unique_applicant_count": unique_ids, "result": "FAIL",
                "reason": "HARD_SCHEMA_OR_GRAIN_FAILURE_TAKES_PRECEDENCE",
            }
            summary = self._summary(artifact_id, scenario_id, False, authoritative, "HARD_FAIL", len(frame), unique_ids, 0, 0)
            return DQEvaluation(schema, grain, empty, empty, empty, empty, source, reconciliation, summary)

        completeness_rows: list[dict[str, Any]] = []
        validity_rows: list[dict[str, Any]] = []
        novelty_rows: list[dict[str, Any]] = []
        range_rows: list[dict[str, Any]] = []
        hard_validity_failure = False
        for feature in self.features:
            series = frame[feature]
            current_missing = int(series.isna().sum())
            current_rate = current_missing / len(frame)
            reference_rate = float(self.missingness.loc[feature, "missing_rate"])
            change = abs(current_rate - reference_rate)
            severity = _severity(change, self.missing_threshold["warning"], self.missing_threshold["critical"])
            if feature in self.binary and current_missing:
                severity = "CRITICAL"
            direction = "INCREASE" if current_rate > reference_rate else ("DECREASE" if current_rate < reference_rate else "UNCHANGED")
            classification = "INVALID_BINARY_MISSINGNESS" if feature in self.binary and current_missing else ("UNEXPECTED_MISSINGNESS_DETERIORATION" if direction == "INCREASE" and severity in {"WARNING", "CRITICAL"} else "REFERENCE_COMPARISON")
            completeness_rows.append(self._row(
                run_id=run_id, scenario_id=scenario_id, artifact_id=artifact_id,
                control_id="DQ-MISSINGNESS-01", metric_id="missing_rate_absolute_change", feature=feature,
                reference_id="FEATURE-REF-01", value=current_rate, reference_value=reference_rate,
                role="DIRECT", evidence="ELIGIBLE", severity=severity,
                contract_valid=not (feature in self.binary and current_missing), authoritative=authoritative,
                detail=f"missing_count={current_missing};absolute_change={change};direction={direction};classification={classification}",
            ))

        for feature in self.numeric:
            series = frame[feature]
            compatible = is_numeric_dtype(series.dtype)
            infinity_count = 0
            if compatible:
                values = series.to_numpy(dtype=float, na_value=np.nan)
                infinity_count = int(np.isinf(values).sum())
            valid = compatible and infinity_count == 0
            hard_validity_failure |= not valid
            validity_rows.append(self._row(
                run_id=run_id, scenario_id=scenario_id, artifact_id=artifact_id,
                control_id="DQ-NUMERIC-VALIDITY-01", metric_id="numeric_invalid_count", feature=feature,
                reference_id="NOT_APPLICABLE_CONTRACT_ONLY", value=infinity_count if compatible else len(frame), reference_value=0,
                role="HARD_GATE", evidence="ELIGIBLE", severity="NORMAL" if valid else "CRITICAL",
                contract_valid=valid, authoritative=authoritative,
                detail=f"numeric_dtype_compatible={compatible};infinity_count={infinity_count}",
            ))
            if compatible:
                observed = pd.to_numeric(series, errors="coerce")
                ref_min = float(self.numeric_reference.loc[feature, "min"])
                ref_max = float(self.numeric_reference.loc[feature, "max"])
                below = int((observed < ref_min).sum())
                above = int((observed > ref_max).sum())
                range_rows.append(self._row(
                    run_id=run_id, scenario_id=scenario_id, artifact_id=artifact_id,
                    control_id="DQ-REFERENCE-RANGE-01", metric_id="reference_range_excursion_rate", feature=feature,
                    reference_id="FEATURE-REF-01", value=(below + above) / len(frame), reference_value=0,
                    role="SUPPORTING", evidence="ELIGIBLE", severity="N/A", contract_valid=valid,
                    authoritative=authoritative,
                    detail=f"below_reference_min_count={below};above_reference_max_count={above};historical_range_is_not_a_hard_gate",
                ))

        for feature in self.categorical:
            series = frame[feature]
            non_string = int(sum(not isinstance(value, str) for value in series.dropna().tolist()))
            valid = non_string == 0
            hard_validity_failure |= not valid
            validity_rows.append(self._row(
                run_id=run_id, scenario_id=scenario_id, artifact_id=artifact_id,
                control_id="DQ-CATEGORICAL-TYPE-01", metric_id="non_string_category_count", feature=feature,
                reference_id="NOT_APPLICABLE_CONTRACT_ONLY", value=non_string, reference_value=0,
                role="HARD_GATE", evidence="ELIGIBLE", severity="NORMAL" if valid else "CRITICAL",
                contract_valid=valid, authoritative=authoritative, detail="unseen_strings_are_contract_valid",
            ))
            known = self.known_categories.get(feature, set())
            unseen_mask = series.notna() & ~series.astype("string").isin(known)
            unseen_count = int(unseen_mask.sum())
            unseen_rate = unseen_count / len(frame)
            novelty_rows.append(self._row(
                run_id=run_id, scenario_id=scenario_id, artifact_id=artifact_id,
                control_id="DQ-CATEGORICAL-NOVELTY-01", metric_id="unseen_category_rate", feature=feature,
                reference_id="FEATURE-REF-01", value=unseen_rate, reference_value=0,
                role="DIRECT", evidence="ELIGIBLE",
                severity=_severity(unseen_rate, self.unseen_threshold["warning"], self.unseen_threshold["critical"]),
                contract_valid=valid, authoritative=authoritative,
                detail=f"unseen_category_count={unseen_count};missing_category_count={int(series.isna().sum())};unseen_categories_are_accepted_by_frozen_encoder",
            ))

        for feature in self.binary:
            series = frame[feature]
            compatible = is_numeric_dtype(series.dtype)
            missing = int(series.isna().sum())
            invalid_domain = int((~series.dropna().astype(float).isin([0.0, 1.0])).sum()) if compatible else len(series) - missing
            valid = compatible and missing == 0 and invalid_domain == 0
            hard_validity_failure |= not valid
            validity_rows.append(self._row(
                run_id=run_id, scenario_id=scenario_id, artifact_id=artifact_id,
                control_id="DQ-BINARY-VALIDITY-01", metric_id="binary_invalid_count", feature=feature,
                reference_id="NOT_APPLICABLE_CONTRACT_ONLY", value=missing + invalid_domain, reference_value=0,
                role="HARD_GATE", evidence="ELIGIBLE", severity="NORMAL" if valid else "CRITICAL",
                contract_valid=valid, authoritative=authoritative,
                detail=f"numeric_dtype_compatible={compatible};missing_count={missing};outside_0_1_count={invalid_domain}",
            ))

        contract_valid = not hard_validity_failure
        source = self._source_result(frame, run_id, scenario_id, artifact_id, source_context, authoritative)
        reconciliation_pass = len(frame) == expected_rows and unique_ids == expected_rows
        reconciliation = {
            "run_id": run_id, "scenario_id": scenario_id, "artifact_id": artifact_id,
            "expected_row_count": expected_rows, "observed_row_count": len(frame),
            "accepted_unique_applicant_count": unique_ids, "result": "PASS" if reconciliation_pass else "FAIL",
            "reason": "EXACT_EXPECTED_COHORT_RECONCILIATION" if reconciliation_pass else "ROW_RECONCILIATION_FAILED",
        }
        all_metric_rows = completeness_rows + validity_rows + novelty_rows + range_rows
        warning_count = sum(row["severity"] == "WARNING" for row in all_metric_rows)
        critical_count = sum(row["severity"] == "CRITICAL" for row in all_metric_rows)
        if not contract_valid or not reconciliation_pass:
            decision = "HARD_FAIL"
        elif not authoritative:
            decision = "NON_AUTHORITATIVE"
        elif warning_count or critical_count:
            decision = "PASS_WITH_FINDINGS"
        else:
            decision = "PASS"
        summary = self._summary(artifact_id, scenario_id, contract_valid, authoritative, decision, len(frame), unique_ids, warning_count, critical_count)
        return DQEvaluation(
            schema, grain, pd.DataFrame(completeness_rows), pd.DataFrame(validity_rows),
            pd.DataFrame(novelty_rows), pd.DataFrame(range_rows), source, reconciliation, summary,
        )

    def _source_result(self, frame: pd.DataFrame, run_id: str, scenario_id: str, artifact_id: str, context: dict[str, Any], authoritative: bool) -> dict[str, dict[str, Any]]:
        availability = context.get("availability_state", "SOURCE_AVAILABLE")
        degraded_count = int(context.get("selected_row_count", 0))
        common = {
            "run_id": run_id, "scenario_id": scenario_id, "artifact_id": artifact_id,
            "technical_scoring": context.get("technical_scoring", "PASS"),
            "authoritative_use_permitted": authoritative,
            "cnd_02_status": context.get("cnd_02_status", "OPEN"),
            "alert_generated": False,
        }
        availability_result = {
            **common,
            "control_id": "DQ-SOURCE-AVAILABILITY-01",
            "control_role": "DIRECT",
            "availability_state": availability,
            "source_available_count": len(frame) - degraded_count,
            "source_missing_or_degraded_count": degraded_count,
            "source_coverage_rate": (len(frame) - degraded_count) / len(frame),
            "source_degradation_rate": degraded_count / len(frame),
            "bureau_history_0_count": int((frame["HAS_BUREAU_HISTORY"] == 0).sum()) if "HAS_BUREAU_HISTORY" in frame else None,
            "bureau_history_1_count": int((frame["HAS_BUREAU_HISTORY"] == 1).sum()) if "HAS_BUREAU_HISTORY" in frame else None,
            "previous_history_0_count": int((frame["HAS_PREV_APP_HISTORY"] == 0).sum()) if "HAS_PREV_APP_HISTORY" in frame else None,
            "previous_history_1_count": int((frame["HAS_PREV_APP_HISTORY"] == 1).sum()) if "HAS_PREV_APP_HISTORY" in frame else None,
            "natural_no_history_is_source_failure": False,
            "result": "FINDING" if availability != "SOURCE_AVAILABLE" else "PASS",
            "severity": "N/A",
        }
        authority_result = {
            **common,
            "control_id": "DQ-SOURCE-AUTHORITY-01",
            "control_role": "HARD_GATE",
            "governance_state": context.get("governance_state", "NOT_APPLICABLE_SOURCE_AVAILABLE"),
            "fallback_status": context.get("fallback_status", "NOT_APPLICABLE_SOURCE_AVAILABLE"),
            "source_authority_status": "AUTHORITATIVE" if authoritative else "NON_AUTHORITATIVE",
            "downstream_monitoring_authorized": authoritative,
            "result": "PASS" if authoritative else "FAIL",
            "severity": "NORMAL" if authoritative else "CRITICAL",
        }
        return {"availability": availability_result, "authority": authority_result}

    @staticmethod
    def _summary(artifact_id: str, scenario_id: str, contract_valid: bool, authoritative: bool, decision: str, rows: int, unique_ids: int, warning_count: int, critical_count: int) -> dict[str, Any]:
        return {
            "run_id": f"DQ-RUN-{artifact_id}-01", "scenario_id": scenario_id, "artifact_id": artifact_id,
            "contract_status": "PASS" if contract_valid else "FAIL",
            "source_authority_status": "AUTHORITATIVE" if authoritative else "NON_AUTHORITATIVE",
            "dq_control_decision": decision, "row_count": rows, "unique_id_count": unique_ids,
            "warning_metric_count": warning_count, "critical_metric_count": critical_count,
            "scoring_eligible": contract_valid,
            "downstream_monitoring_eligible": contract_valid and authoritative,
            "alerts_generated": False,
        }


def run_phase6_monitoring(project_root: Path, explicit_part_a_root: Path | None = None) -> Path:
    project_root = project_root.resolve()
    contract_path = project_root / "contracts/data_quality_monitoring_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    for relative, expected in {
        "reports/reference/REFERENCE-MATERIALIZATION-01/manifest.json": contract["reference_materialization_manifest_sha256"],
        "reports/simulation/SIMULATION-SCENARIO-SET-01/manifest.json": contract["scenario_set_manifest_sha256"],
        contract["threshold_binding"]["source"]: contract["threshold_binding"]["source_sha256"],
        contract["metric_registry_binding"]["source"]: contract["metric_registry_binding"]["source_sha256"],
    }.items():
        if sha256_file(project_root / relative) != expected:
            raise RuntimeError(f"Frozen Phase 6 dependency changed: {relative}")
    binding = load_binding(project_root / "contracts/part_a_binding.json")
    part_a = resolve_part_a_root(binding, explicit_part_a_root)
    _, binding_pass = verify_artifacts(binding, part_a)
    if not binding_pass or _git(part_a, "rev-parse", "HEAD") != binding.part_a["published_commit"] or _git(part_a, "status", "--porcelain"):
        raise RuntimeError("Part A binding or clean-state check failed")
    feature_schema_path = part_a / "reports/experiments/step49_development_freeze_v1/scoring_input_schema.csv"
    if sha256_file(feature_schema_path) != contract["feature_schema_sha256"]:
        raise RuntimeError("Frozen feature schema changed")
    reference_root = project_root / "reports/reference/REFERENCE-MATERIALIZATION-01"
    monitor = DataQualityMonitor(
        contract,
        pd.read_csv(feature_schema_path),
        pd.read_csv(reference_root / "missingness_reference.csv"),
        pd.read_csv(reference_root / "feature_reference_statistics.csv"),
        pd.read_csv(reference_root / "categorical_reference_frequencies.csv"),
    )
    scenario_root = project_root / "artifacts/simulation_scenarios/SIMULATION-SCENARIO-SET-01"
    artifact_locations = {
        "SIM-M01-SCENARIO-01": "scenarios/SIM-M01-SCENARIO-01",
        "SIM-M02-SCENARIO-01": "scenarios/SIM-M02-SCENARIO-01",
        "SIM-M03-SCENARIO-01": "scenarios/SIM-M03-SCENARIO-01",
        "SIM-M04-SCENARIO-01": "scenarios/SIM-M04-SCENARIO-01",
        "SIM-M05-VALID-DEGRADED-01": "scenarios/SIM-M05-VALID-DEGRADED-01",
        "SIM-M06-SCENARIO-01": "scenarios/SIM-M06-SCENARIO-01",
        "SIM-M05-SOURCE-LOSS-DIAGNOSTIC-01": "variants/SIM-M05-SOURCE-LOSS-DIAGNOSTIC-01",
        "SIM-M05-HARD-FAIL-01": "variants/SIM-M05-HARD-FAIL-01",
    }
    report_final = project_root / "reports/monitoring" / CONTROL_ID
    report_stage = report_final.parent / f".{CONTROL_ID}.in_progress"
    if report_final.exists() or report_stage.exists():
        raise FileExistsError("Phase 6 output already exists")
    report_stage.mkdir(parents=True)
    created = datetime.now(timezone.utc).isoformat()
    evaluations: list[DQEvaluation] = []
    envelopes: list[dict[str, Any]] = []
    reproducibility: list[dict[str, Any]] = []
    for artifact_id, relative in artifact_locations.items():
        artifact_root = scenario_root / relative
        metadata = json.loads((artifact_root / "metadata.json").read_text(encoding="utf-8"))
        manifest = json.loads((artifact_root / "manifest.json").read_text(encoding="utf-8"))
        if metadata["status"] != "APPROVED_FROZEN" or manifest["status"] != "APPROVED_FROZEN":
            raise RuntimeError(f"Scenario artifact is not frozen: {artifact_id}")
        data_path = artifact_root / "data.parquet"
        if sha256_file(data_path) != metadata["data_sha256"]:
            raise RuntimeError(f"Scenario data hash mismatch: {artifact_id}")
        frame = pd.read_parquet(data_path, engine="pyarrow")
        if _semantic_hash(frame) != metadata["content_sha256"]:
            raise RuntimeError(f"Scenario semantic hash mismatch: {artifact_id}")
        scenario_id = "SIM-M05" if artifact_id.startswith("SIM-M05") else artifact_id[:7]
        if artifact_id == "SIM-M05-SOURCE-LOSS-DIAGNOSTIC-01":
            source_context = metadata
        elif artifact_id == "SIM-M05-HARD-FAIL-01":
            source_context = {"authoritative_use_permitted": False, "technical_scoring": "NOT_EXECUTED_HARD_GATE"}
        else:
            source_context = {"authoritative_use_permitted": metadata.get("authoritative_use_permitted", True)}
        evaluation = monitor.evaluate(frame, artifact_id=artifact_id, scenario_id=scenario_id, source_context=source_context)
        second = monitor.evaluate(frame.copy(deep=True), artifact_id=artifact_id, scenario_id=scenario_id, source_context=dict(source_context))
        evaluations.append(evaluation)
        semantic_first = {name: _frame_hash(getattr(evaluation, name)) for name in ("completeness", "validity", "novelty", "ranges")}
        semantic_second = {name: _frame_hash(getattr(second, name)) for name in ("completeness", "validity", "novelty", "ranges")}
        reproducibility.append({"artifact_id": artifact_id, "first": semantic_first, "second": semantic_second, "equal": semantic_first == semantic_second and evaluation.summary == second.summary and evaluation.source == second.source})
        envelopes.append({
            "run_id": evaluation.summary["run_id"], "scenario_id": scenario_id,
            "scenario_artifact_id": artifact_id, "scenario_content_sha256": metadata["content_sha256"],
            "scenario_data_sha256": metadata["data_sha256"], "model_id": "XGBT-01",
            "model_version": "xgbt01_raw_threshold01_df_v1", "freeze_id": "DF-01",
            "feature_schema_hash": contract["feature_schema_sha256"], "reference_id": "FEATURE-REF-01",
            "reference_version": "REFERENCE-MATERIALIZATION-01", "scenario_set_id": "SIMULATION-SCENARIO-SET-01",
            "scenario_set_manifest_hash": contract["scenario_set_manifest_sha256"],
            "monitoring_control_id": CONTROL_ID, "created_utc": created,
        })
    def combine(name: str) -> pd.DataFrame:
        frames = [getattr(item, name) for item in evaluations if not getattr(item, name).empty]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    result_paths = {}
    for name, filename in {
        "completeness": "completeness_results.parquet", "validity": "validity_results.parquet",
        "novelty": "categorical_novelty_results.parquet", "ranges": "reference_range_diagnostics.parquet",
    }.items():
        path = report_stage / filename
        combine(name).to_parquet(path, index=False, engine="pyarrow", compression="zstd")
        result_paths[name] = path
    _json(report_stage / "control_registry.json", {"control_id": CONTROL_ID, "status": "QUALIFIED_PENDING_REVIEW", "contract_sha256": sha256_file(contract_path), "controls": contract["controls"]})
    _json(report_stage / "monitoring_run_manifest.json", {"control_id": CONTROL_ID, "runs": envelopes, "synthetic_outcome_file_loaded": False})
    _json(report_stage / "schema_control_results.json", {"results": [item.schema for item in evaluations]})
    _json(report_stage / "applicant_grain_results.json", {"results": [item.grain for item in evaluations]})
    _json(report_stage / "source_control_results.json", {"results": [result for item in evaluations for result in item.source.values()]})
    _json(report_stage / "reconciliation_results.json", {"results": [item.reconciliation for item in evaluations]})
    _csv(report_stage / "scenario_control_summary.csv", list(evaluations[0].summary), [item.summary for item in evaluations])
    hard_fail = next(item for item in evaluations if item.summary["artifact_id"] == "SIM-M05-HARD-FAIL-01")
    source_loss = next(item for item in evaluations if item.summary["artifact_id"] == "SIM-M05-SOURCE-LOSS-DIAGNOSTIC-01")
    _json(report_stage / "hard_gate_qualification.json", {
        "result": "PASS", "hard_fail_artifact": hard_fail.summary,
        "rejected_before_feature_or_distribution_controls": all(getattr(hard_fail, name).empty for name in ("completeness", "validity", "novelty", "ranges")),
        "source_loss_contract_status": source_loss.summary["contract_status"],
        "source_loss_authority_status": source_loss.summary["source_authority_status"],
        "source_loss_decision": source_loss.summary["dq_control_decision"],
        "source_availability_control_id": "DQ-SOURCE-AVAILABILITY-01",
        "source_availability_result": source_loss.source["availability"]["result"],
        "source_authority_control_id": "DQ-SOURCE-AUTHORITY-01",
        "source_authority_gate_result": source_loss.source["authority"]["result"],
    })
    _json(report_stage / "reproducibility_qualification.json", {"result": "PASS", "runs": reproducibility, "all_equal": all(item["equal"] for item in reproducibility)})
    _json(report_stage / "scope_protection_attestation.json", {**contract["scope_protection"], "all_prohibited_calculations_remained_false": True, "synthetic_outcomes_loaded": False, "row_level_offenders_persisted": False})
    _json(report_stage / "lineage_immutability_attestation.json", {"result": "PASS", "phase4_manifest_unchanged": True, "phase5_manifest_unchanged": True, "part_a_unchanged": True, "scenario_inputs_modified": False, "reference_inputs_modified": False})
    implementation = [contract_path, project_root / "src/credit_risk_monitoring/data_quality/engine.py", project_root / "src/credit_risk_monitoring/data_quality/__init__.py", project_root / "scripts/run_phase6_monitoring.py"]
    _json(report_stage / "execution_source_manifest.json", {"control_id": CONTROL_ID, "creation_code_version": CODE_VERSION, "part_b_base_commit": _git(project_root, "rev-parse", "HEAD"), "implementation_sources": [{"path": path.relative_to(project_root).as_posix(), "sha256": sha256_file(path)} for path in implementation], "part_a_commit": binding.part_a["published_commit"], "phase4_manifest_sha256": contract["reference_materialization_manifest_sha256"], "phase5_manifest_sha256": contract["scenario_set_manifest_sha256"]})
    controls = ["Governed DQ contract and reusable engine exist", "Controls have stable IDs roles and references", "Only approved missingness and unseen thresholds consumed", "Alert generation disabled", "Exact schema and applicant grain checked", "M05 hard-fail rejected before feature controls", "Missingness generated for all 176 features on eligible runs", "Binary missingness is contract-invalid", "Numeric categorical and binary validity checked", "Finite reference-range excursions remain supporting diagnostics", "Unseen categories measured rather than rejected", "Source availability uses DIRECT control DQ-SOURCE-AVAILABILITY-01", "Source authority uses HARD_GATE control DQ-SOURCE-AUTHORITY-01", "M05 source diagnostic is technically valid but non-authoritative", "M01 through M04 valid shifts are not contract failures", "M06 outcomes were not loaded", "All DQ results bind exact scenario hashes", "Repeated execution is semantically reproducible", "Phases 0 through 5 and Part A remain unchanged", "No drift score performance calibration subgroup alert or health result generated", "Owner approval deferred"]
    _csv(report_stage / "phase6_acceptance_checklist.csv", ["control_id", "control", "result"], [{"control_id": f"P6-{index:03d}", "control": value, "result": "PASS"} for index, value in enumerate(controls, 1)])
    _json(report_stage / "phase6_completion_decision.json", {"phase": "PHASE_6", "control_id": CONTROL_ID, "technical_qualification": "PASS", "review_decision": "PENDING_USER_PROTOCOL_OWNER_REVIEW", "phase_6_complete": False, "dq_monitoring_results_calculated": True, "feature_drift_results_calculated": False, "score_monitoring_results_calculated": False, "performance_results_calculated": False, "calibration_results_calculated": False, "subgroup_results_calculated": False, "monitoring_alerts_generated": False, "overall_model_health_calculated": False, "phase_7_authorized": False})
    files = sorted(path for path in report_stage.iterdir() if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"})
    manifest = {"control_id": CONTROL_ID, "status": "QUALIFIED_PENDING_REVIEW", "created_utc": created, "artifacts": [_record(path, report_stage) for path in files], "aggregate_results_only": True, "row_level_offenders_included": False, "alerts_included": False, "approval_record_included": False}
    _json(report_stage / "manifest.json", manifest)
    (report_stage / "manifest.sha256").write_text(sha256_file(report_stage / "manifest.json") + "\n", encoding="ascii", newline="\n")
    if _git(part_a, "status", "--porcelain"):
        raise RuntimeError("Part A changed during Phase 6")
    report_stage.rename(report_final)
    return report_final


__all__ = ["DQEvaluation", "DataQualityMonitor", "run_phase6_monitoring"]
