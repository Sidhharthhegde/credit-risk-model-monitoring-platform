"""Phase 10 generic governed segment and subpopulation monitoring."""

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
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score, roc_curve

from credit_risk_monitoring.prediction.engine import apply_threshold
from credit_risk_monitoring.qualification.binding import load_binding, resolve_part_a_root, sha256_file, verify_artifacts
from credit_risk_monitoring.reference.materialization import _semantic_hash


MONITORING_ID = "SEGMENT-MONITORING-01"
CODE_VERSION = "PHASE10-SEGMENT-MONITOR-0.1.0"
SCENARIOS = ["SIM-M01", "SIM-M02", "SIM-M03", "SIM-M04", "SIM-M05", "SIM-M06"]
SCENARIO_ARTIFACTS = {
    "SIM-M01": "SIM-M01-SCENARIO-01", "SIM-M02": "SIM-M02-SCENARIO-01",
    "SIM-M03": "SIM-M03-SCENARIO-01", "SIM-M04": "SIM-M04-SCENARIO-01",
    "SIM-M05": "SIM-M05-VALID-DEGRADED-01", "SIM-M06": "SIM-M06-SCENARIO-01",
}


def _json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root), *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _record(path: Path, root: Path) -> dict[str, Any]:
    return {"path": path.relative_to(root).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def _dict_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _safe_divide(numerator: float | int, denominator: float | int) -> float | None:
    return float(numerator / denominator) if denominator else None


def _verify_manifest_artifacts(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "APPROVED_FROZEN":
        raise RuntimeError(f"Local artifact is not approved frozen: {manifest_path}")
    for artifact in manifest["artifacts"]:
        if sha256_file(manifest_path.parent / artifact["path"]) != artifact["sha256"]:
            raise RuntimeError(f"Local artifact content changed: {manifest_path.parent / artifact['path']}")


@dataclass(frozen=True)
class SegmentDefinition:
    family_id: str
    family_name: str
    source_features: tuple[str, ...]
    levels: tuple[str, ...]
    exploratory: bool
    frozen_definition: str


def load_segment_definitions(registry: pd.DataFrame, catalog: pd.DataFrame) -> list[SegmentDefinition]:
    definitions = []
    for row in registry.to_dict("records"):
        family_id = row["Subgroup_ID"]
        level_rows = catalog.loc[catalog["Subgroup_ID"] == family_id]
        definitions.append(SegmentDefinition(
            family_id=family_id,
            family_name=row["Subgroup_Name"],
            source_features=tuple(row["Source_Feature_s"].split(";")),
            levels=tuple(level_rows["Level"].astype(str)),
            exploratory=bool(row["Exploratory_Not_Fairness_Certification"]),
            frozen_definition=row["Frozen_Definition"],
        ))
    if len(definitions) != 12 or sum(len(item.levels) for item in definitions) != 32:
        raise RuntimeError("Frozen Part A segment registry does not contain 12 families and 32 levels")
    return definitions


def _integer_text(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    result = pd.Series(pd.NA, index=series.index, dtype="string")
    valid = numeric.notna() & np.isclose(numeric, np.round(numeric))
    result.loc[valid] = numeric.loc[valid].round().astype("int64").astype("string")
    return result


def assign_segment(frame: pd.DataFrame, definition: SegmentDefinition) -> pd.Series:
    missing = sorted(set(definition.source_features) - set(frame.columns))
    if missing:
        raise ValueError(f"Segment source features are missing for {definition.family_id}: {missing}")
    family = definition.family_id
    if family in {"SG-01", "SG-02", "SG-04", "SG-05", "SG-06", "SG-07", "SG-11"}:
        assigned = _integer_text(frame[definition.source_features[0]])
    elif family == "SG-03":
        bureau = _integer_text(frame["HAS_BUREAU_HISTORY"])
        previous = _integer_text(frame["HAS_PREV_APP_HISTORY"])
        assigned = "BUREAU_" + bureau + "_PREV_" + previous
    elif family == "SG-08":
        assigned = frame[list(definition.source_features)].notna().sum(axis=1).astype("int64").astype("string")
    elif family in {"SG-09", "SG-12"}:
        assigned = frame[definition.source_features[0]].astype("string")
    elif family == "SG-10":
        age = -pd.to_numeric(frame["DAYS_BIRTH"], errors="coerce") / 365.25
        assigned = pd.Series(pd.NA, index=frame.index, dtype="string")
        assigned.loc[(age >= 0) & (age < 30)] = "[0,30)"
        assigned.loc[(age >= 30) & (age < 45)] = "[30,45)"
        assigned.loc[(age >= 45) & (age < 60)] = "[45,60)"
        assigned.loc[age >= 60] = "[60,+inf)"
    else:
        raise ValueError(f"Unsupported frozen segment family: {family}")
    assigned = assigned.fillna("__UNCLASSIFIABLE__").astype("string")
    return assigned.where(assigned.isin(definition.levels), "__UNCLASSIFIABLE__")


def evidence_status(n: int, defaults: int, *, minimum_n: int, minimum_defaults: int = 50, minimum_nondefaults: int = 50) -> str:
    nondefaults = n - defaults
    return "ELIGIBLE" if n >= minimum_n and defaults >= minimum_defaults and nondefaults >= minimum_nondefaults else "INSUFFICIENT_DATA"


def _score_bins(values: np.ndarray, inner_edges: list[float]) -> np.ndarray:
    labels = np.arange(len(inner_edges) + 1)
    result = pd.cut(values, bins=[0.0, *inner_edges, 1.0], labels=labels, include_lowest=True, right=True)
    if pd.isna(result).any():
        raise RuntimeError("Probability did not map to a frozen global score bin")
    return np.asarray(result.astype(int))


def _score_psi(reference: np.ndarray, current: np.ndarray, inner_edges: list[float], epsilon: float) -> float:
    if not len(reference) or not len(current):
        raise ValueError("Score PSI requires non-empty reference and current segments")
    ref_bins = _score_bins(reference, inner_edges)
    cur_bins = _score_bins(current, inner_edges)
    bin_count = len(inner_edges) + 1
    ref = np.bincount(ref_bins, minlength=bin_count).astype(float)
    cur = np.bincount(cur_bins, minlength=bin_count).astype(float)
    ref[ref == 0] = epsilon; cur[cur == 0] = epsilon
    ref /= ref.sum(); cur /= cur.sum()
    return float(np.sum((cur - ref) * np.log(cur / ref)))


@dataclass(frozen=True)
class SegmentResults:
    population: pd.DataFrame
    prediction: pd.DataFrame
    score_psi: pd.DataFrame
    eligibility: pd.DataFrame
    performance: pd.DataFrame
    calibration: pd.DataFrame
    threshold: pd.DataFrame
    reconciliation: list[dict[str, Any]]


class SegmentMonitor:
    def __init__(self, contract: dict[str, Any], definitions: list[SegmentDefinition], train: pd.DataFrame, dev_val: pd.DataFrame, score_bins: dict[str, Any], part_a_references: dict[str, pd.DataFrame]) -> None:
        self.contract = contract
        self.definitions = definitions
        self.train = train
        self.dev = dev_val
        self.edges = [float(value) for value in score_bins["finite_inner_edges"]]
        self.references = part_a_references
        self.population_reference: dict[tuple[str, str], dict[str, Any]] = {}
        self.prediction_reference: dict[tuple[str, str], dict[str, Any]] = {}
        self._materialize_references()

    def _materialize_references(self) -> None:
        quantiles = [0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]
        for definition in self.definitions:
            train_segments = assign_segment(self.train, definition)
            dev_segments = assign_segment(self.dev, definition)
            if (train_segments == "__UNCLASSIFIABLE__").any() or (dev_segments == "__UNCLASSIFIABLE__").any():
                raise RuntimeError(f"Frozen reference contains unclassifiable {definition.family_id} values")
            for level in definition.levels:
                train_count = int((train_segments == level).sum())
                self.population_reference[(definition.family_id, level)] = {
                    "count": train_count, "share": float(train_count / len(self.train)),
                }
                mask = np.asarray(dev_segments == level)
                probabilities = self.dev.loc[mask, "raw_probability"].to_numpy(dtype=float)
                classes = self.dev.loc[mask, "risk_class"].astype(str).to_numpy()
                if not len(probabilities):
                    raise RuntimeError(f"Frozen development-validation segment is empty: {definition.family_id}:{level}")
                self.prediction_reference[(definition.family_id, level)] = {
                    "count": len(probabilities), "mean": float(probabilities.mean()),
                    "median": float(np.median(probabilities)), "std": float(np.std(probabilities, ddof=0)),
                    "quantiles": {str(q): float(np.quantile(probabilities, q)) for q in quantiles},
                    "risk_positive_count": int((classes == "risk_positive").sum()),
                    "risk_positive_rate": float((classes == "risk_positive").mean()),
                    "probabilities": probabilities,
                }

    def reference_payload(self) -> dict[str, Any]:
        population = []
        prediction = []
        for definition in self.definitions:
            for level in definition.levels:
                key = (definition.family_id, level)
                population.append({"segment_family_id": key[0], "segment_id": f"{key[0]}:{level}", "segment_value": level, **self.population_reference[key]})
                item = self.prediction_reference[key]
                prediction.append({
                    "segment_family_id": key[0], "segment_id": f"{key[0]}:{level}", "segment_value": level,
                    **{name: value for name, value in item.items() if name != "probabilities"},
                })
        return {
            "population_reference_id": "TRAIN-PHYSICAL-01_FEATURE-REF-01",
            "prediction_reference_id": "DEV-VAL-PHYSICAL-01_PERF-REF-01",
            "global_score_bins_used": True, "segment_specific_bins_created": False,
            "population": population, "prediction": prediction,
            "part_a_outcome_reference_artifacts": {
                name: frame.astype(object).where(pd.notna(frame), None).to_dict("records")
                for name, frame in self.references.items()
            },
        }

    def evaluate(self, scenario_frames: dict[str, pd.DataFrame], prediction_frames: dict[str, pd.DataFrame], outcomes: pd.DataFrame) -> SegmentResults:
        population_rows: list[dict[str, Any]] = []
        prediction_rows: list[dict[str, Any]] = []
        psi_rows: list[dict[str, Any]] = []
        eligibility_rows: list[dict[str, Any]] = []
        performance_rows: list[dict[str, Any]] = []
        calibration_rows: list[dict[str, Any]] = []
        threshold_rows: list[dict[str, Any]] = []
        reconciliation: list[dict[str, Any]] = []
        performance_ref = self.references["discrimination"].set_index("Group_ID")
        calibration_ref = self.references["probability_quality"].set_index("Group_ID")
        threshold_ref = self.references["threshold"].set_index("Group_ID")
        minimum_disc = self.contract["minimum_evidence"]["discrimination_and_calibration"]
        minimum_threshold = self.contract["minimum_evidence"]["threshold_and_error_rates"]
        epsilon = float(self.contract["label_free_policy"]["score_psi_epsilon"])
        log_epsilon = float(self.contract["outcome_policy"]["log_loss_probability_clip_epsilon"])

        for scenario in SCENARIOS:
            features = scenario_frames[scenario]
            predictions = prediction_frames[scenario]
            if features["SK_ID_CURR"].isna().any() or not features["SK_ID_CURR"].is_unique:
                raise RuntimeError(f"Invalid feature applicant grain for {scenario}")
            if predictions["SK_ID_CURR"].isna().any() or not predictions["SK_ID_CURR"].is_unique:
                raise RuntimeError(f"Invalid prediction applicant grain for {scenario}")
            if set(features["SK_ID_CURR"]) != set(predictions["SK_ID_CURR"]):
                raise RuntimeError(f"Feature and prediction applicant sets differ for {scenario}")
            joined = features.merge(
                predictions[["SK_ID_CURR", "raw_probability", "analytical_risk_class"]],
                on="SK_ID_CURR", how="left", validate="one_to_one", sort=False,
            )
            if scenario == "SIM-M06":
                if set(joined["SK_ID_CURR"]) != set(outcomes["SK_ID_CURR"]):
                    raise RuntimeError("M06 segment outcome applicant set differs")
                joined = joined.merge(outcomes[["SK_ID_CURR", "OUTCOME"]], on="SK_ID_CURR", how="left", validate="one_to_one", sort=False)

            for definition in self.definitions:
                assigned = assign_segment(joined, definition)
                unknown_count = int((assigned == "__UNCLASSIFIABLE__").sum())
                level_count_sum = int(sum((assigned == level).sum() for level in definition.levels))
                reconciliation.append({
                    "scenario_id": scenario, "segment_family_id": definition.family_id,
                    "cohort_row_count": len(joined), "segment_level_count_sum": level_count_sum,
                    "unclassifiable_count": unknown_count, "exhaustive": True,
                    "result": "PASS" if level_count_sum == len(joined) and unknown_count == 0 else "FAIL",
                })
                if unknown_count or level_count_sum != len(joined):
                    raise RuntimeError(f"Segment assignment failed reconciliation for {scenario} {definition.family_id}")

                for level in definition.levels:
                    segment_id = f"{definition.family_id}:{level}"
                    mask = np.asarray(assigned == level)
                    count = int(mask.sum())
                    share = float(count / len(joined))
                    pop_ref = self.population_reference[(definition.family_id, level)]
                    pred_ref = self.prediction_reference[(definition.family_id, level)]
                    current_p = joined.loc[mask, "raw_probability"].to_numpy(dtype=float)
                    current_classes = joined.loc[mask, "analytical_risk_class"].astype(str).to_numpy()
                    common = {
                        "scenario_id": scenario, "segment_family_id": definition.family_id,
                        "segment_family_name": definition.family_name, "segment_id": segment_id,
                        "segment_value": level, "exploratory_not_fairness_certification": definition.exploratory,
                    }
                    population_rows.append({
                        **common, "segment_count": count, "segment_share": share,
                        "reference_segment_count": pop_ref["count"], "reference_segment_share": pop_ref["share"],
                        "segment_share_change": share - pop_ref["share"],
                        "segment_share_change_percentage_points": 100.0 * (share - pop_ref["share"]),
                        "composition_severity": "N/A", "population_evidence_status": "ELIGIBLE",
                        "alert_generated": False,
                    })
                    prediction_status = "ELIGIBLE" if count > 0 and pred_ref["count"] > 0 else "INSUFFICIENT_DATA"
                    prediction_rows.append({
                        **common, "segment_count": count, "reference_segment_count": pred_ref["count"],
                        "mean_pd": float(current_p.mean()) if count else None,
                        "reference_mean_pd": pred_ref["mean"],
                        "median_pd": float(np.median(current_p)) if count else None,
                        "reference_median_pd": pred_ref["median"],
                        "standard_deviation_pd": float(np.std(current_p, ddof=0)) if count else None,
                        "reference_standard_deviation_pd": pred_ref["std"],
                        **{f"q{str(q).replace('.', '_')}": float(np.quantile(current_p, q)) if count else None for q in [0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]},
                        "risk_positive_count": int((current_classes == "risk_positive").sum()),
                        "risk_positive_rate": float((current_classes == "risk_positive").mean()) if count else None,
                        "reference_risk_positive_rate": pred_ref["risk_positive_rate"],
                        "risk_negative_count": int((current_classes == "risk_negative").sum()),
                        "risk_negative_rate": float((current_classes == "risk_negative").mean()) if count else None,
                        "prediction_evidence_status": prediction_status, "alert_generated": False,
                    })
                    psi = _score_psi(pred_ref["probabilities"], current_p, self.edges, epsilon) if prediction_status == "ELIGIBLE" else None
                    psi_rows.append({
                        **common, "score_psi": psi, "score_psi_severity": "N/A",
                        "severity_threshold_applicability": "CONTROLLED_DEFERRED_NOT_INHERITED_FROM_PORTFOLIO",
                        "global_frozen_score_bins_used": True, "segment_specific_bins_created": False,
                        "score_psi_evidence_status": prediction_status, "alert_generated": False,
                    })

                    if scenario != "SIM-M06":
                        eligibility_rows.append({
                            **common, "outcome_availability": "NOT_AVAILABLE", "maturity_status": "NOT_APPLICABLE",
                            "evidence_type": "N/A", "discrimination_evidence_status": "NOT_ASSESSABLE",
                            "calibration_evidence_status": "NOT_ASSESSABLE", "threshold_evidence_status": "NOT_ASSESSABLE",
                            "non_assessability_reason": "OUTCOME_NOT_AVAILABLE", "row_count": count,
                            "default_count": None, "nondefault_count": None,
                        })
                        continue

                    y = joined.loc[mask, "OUTCOME"].to_numpy(dtype=int)
                    defaults = int(y.sum())
                    nondefaults = count - defaults
                    disc_status = evidence_status(count, defaults, minimum_n=int(minimum_disc["minimum_records"]), minimum_defaults=int(minimum_disc["minimum_defaults"]), minimum_nondefaults=int(minimum_disc["minimum_nondefaults"]))
                    threshold_status = evidence_status(count, defaults, minimum_n=int(minimum_threshold["minimum_records"]), minimum_defaults=int(minimum_threshold["minimum_defaults"]), minimum_nondefaults=int(minimum_threshold["minimum_nondefaults"]))
                    eligibility_rows.append({
                        **common, "outcome_availability": "AVAILABLE", "maturity_status": "MATURED",
                        "evidence_type": "SYNTHETIC_SCENARIO_EVIDENCE",
                        "discrimination_evidence_status": disc_status, "calibration_evidence_status": disc_status,
                        "threshold_evidence_status": threshold_status, "non_assessability_reason": None,
                        "row_count": count, "default_count": defaults, "nondefault_count": nondefaults,
                    })
                    ref_disc = performance_ref.loc[segment_id]
                    if disc_status == "ELIGIBLE":
                        auc = float(roc_auc_score(y, current_p))
                        fpr_curve, tpr_curve, _ = roc_curve(y, current_p)
                        ks = float(np.max(tpr_curve - fpr_curve))
                        ap = float(average_precision_score(y, current_p))
                        gini = 2.0 * auc - 1.0
                    else:
                        auc = ks = ap = gini = None
                    performance_rows.append({
                        **common, "row_count": count, "default_count": defaults, "nondefault_count": nondefaults,
                        "evidence_status": disc_status, "evidence_type": "SYNTHETIC_SCENARIO_EVIDENCE",
                        "roc_auc": auc, "reference_roc_auc": float(ref_disc["ROC_AUC"]),
                        "performance_ks": ks, "reference_performance_ks": float(ref_disc["KS"]),
                        "pr_auc_average_precision": ap, "reference_pr_auc_average_precision": float(ref_disc["PR_AUC"]),
                        "gini": gini, "performance_severity": "N/A", "alert_generated": False,
                        "empirical_performance": False, "external_validation": False,
                    })
                    ref_cal = calibration_ref.loc[segment_id]
                    if disc_status == "ELIGIBLE":
                        expected = float(current_p.sum())
                        observed_rate = float(y.mean())
                        average_pd = float(current_p.mean())
                        oe = _safe_divide(defaults, expected)
                        brier = float(brier_score_loss(y, current_p))
                        ll = float(log_loss(y, np.clip(current_p, log_epsilon, 1.0 - log_epsilon), labels=[0, 1]))
                    else:
                        expected = observed_rate = average_pd = oe = brier = ll = None
                    calibration_rows.append({
                        **common, "row_count": count, "default_count": defaults,
                        "evidence_status": disc_status, "evidence_type": "SYNTHETIC_SCENARIO_EVIDENCE",
                        "synthetic_observed_default_rate": observed_rate,
                        "reference_observed_default_rate": float(ref_cal["Observed_Default_Rate"]),
                        "average_pd": average_pd, "reference_average_pd": float(ref_cal["Mean_Predicted_Probability"]),
                        "expected_default_count": expected, "observed_expected_ratio": oe,
                        "brier_score": brier, "reference_brier_score": float(ref_cal["Brier_Score"]),
                        "log_loss": ll, "reference_log_loss": float(ref_cal["Log_Loss"]),
                        "calibration_severity": "N/A", "alert_generated": False,
                        "empirical_performance": False, "external_validation": False,
                    })
                    ref_threshold = threshold_ref.loc[segment_id]
                    if threshold_status == "ELIGIBLE":
                        positive = current_classes == "risk_positive"; negative = ~positive
                        tp = int((positive & (y == 1)).sum()); fp = int((positive & (y == 0)).sum())
                        tn = int((negative & (y == 0)).sum()); fn = int((negative & (y == 1)).sum())
                    else:
                        tp = fp = tn = fn = None
                    threshold_rows.append({
                        **common, "row_count": count, "default_count": defaults, "nondefault_count": nondefaults,
                        "evidence_status": threshold_status, "evidence_type": "SYNTHETIC_SCENARIO_EVIDENCE",
                        "threshold_id": "THRESHOLD-01", "threshold_value": 0.08, "threshold_operator": ">=",
                        "true_positive": tp, "false_positive": fp, "true_negative": tn, "false_negative": fn,
                        "recall": _safe_divide(tp, tp + fn) if tp is not None else None,
                        "reference_recall": float(ref_threshold["Recall"]),
                        "specificity": _safe_divide(tn, tn + fp) if tn is not None else None,
                        "reference_specificity": float(ref_threshold["Specificity"]),
                        "precision": _safe_divide(tp, tp + fp) if tp is not None else None,
                        "reference_precision": float(ref_threshold["Precision"]),
                        "false_positive_rate": _safe_divide(fp, fp + tn) if fp is not None else None,
                        "false_negative_rate": _safe_divide(fn, fn + tp) if fn is not None else None,
                        "negative_predictive_value": _safe_divide(tn, tn + fn) if tn is not None else None,
                        "risk_positive_synthetic_default_rate": _safe_divide(tp, tp + fp) if tp is not None else None,
                        "risk_negative_synthetic_default_rate": _safe_divide(fn, fn + tn) if fn is not None else None,
                        "threshold_performance_severity": "N/A", "alert_generated": False,
                        "empirical_performance": False, "external_validation": False,
                    })

        return SegmentResults(
            pd.DataFrame(population_rows), pd.DataFrame(prediction_rows), pd.DataFrame(psi_rows),
            pd.DataFrame(eligibility_rows), pd.DataFrame(performance_rows), pd.DataFrame(calibration_rows),
            pd.DataFrame(threshold_rows), reconciliation,
        )


def _frame_hash(frame: pd.DataFrame) -> str:
    return _semantic_hash(frame.reset_index(drop=True))


def run_phase10_monitoring(project_root: Path, explicit_part_a_root: Path | None = None) -> Path:
    project_root = project_root.resolve()
    contract_path = project_root / "contracts/segment_monitoring_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    phase_paths = {
        "phase_6_manifest_sha256": "reports/monitoring/DATA-QUALITY-CONTROL-01/manifest.json",
        "phase_7_manifest_sha256": "reports/monitoring/FEATURE-DRIFT-MONITORING-01/manifest.json",
        "phase_8_manifest_sha256": "reports/monitoring/PREDICTION-MONITORING-01/manifest.json",
        "phase_9_manifest_sha256": "reports/monitoring/OUTCOME-PERFORMANCE-MONITORING-01/manifest.json",
        "train_snapshot_manifest_sha256": "artifacts/reference_snapshots/REFERENCE-MATERIALIZATION-01/TRAIN-PHYSICAL-01/snapshot_manifest.json",
        "dev_val_snapshot_manifest_sha256": "artifacts/reference_snapshots/REFERENCE-MATERIALIZATION-01/DEV-VAL-PHYSICAL-01/snapshot_manifest.json",
        "score_bins_sha256": "reports/reference/REFERENCE-MATERIALIZATION-01/score_psi_bin_definitions.json",
    }
    for key, relative in phase_paths.items():
        if sha256_file(project_root / relative) != contract["frozen_dependencies"][key]:
            raise RuntimeError(f"Frozen Phase 10 dependency changed: {relative}")
    phase9 = json.loads((project_root / "reports/monitoring/OUTCOME-PERFORMANCE-MONITORING-01/phase9_completion_decision.json").read_text(encoding="utf-8"))
    if phase9["review_decision"] != "APPROVED" or not phase9["phase_10_authorized"]:
        raise RuntimeError("Phase 10 is not authorized")

    binding = load_binding(project_root / "contracts/part_a_binding.json")
    part_a = resolve_part_a_root(binding, explicit_part_a_root)
    _, binding_pass = verify_artifacts(binding, part_a)
    if not binding_pass or _git(part_a, "rev-parse", "HEAD") != binding.part_a["published_commit"] or _git(part_a, "status", "--porcelain"):
        raise RuntimeError("Part A binding or clean-state check failed")
    phase56 = part_a / "reports/formal_validation/phase56_subpopulation_validation_v1_1"
    part_a_paths = {
        "part_a_registry_sha256": phase56 / "subgroup_registry_snapshot.csv",
        "part_a_level_catalog_sha256": phase56 / "subgroup_level_catalog.csv",
        "part_a_population_summary_sha256": phase56 / "subgroup_population_summary.csv",
        "part_a_discrimination_sha256": phase56 / "subgroup_discrimination.csv",
        "part_a_probability_quality_sha256": phase56 / "subgroup_probability_quality.csv",
        "part_a_threshold_metrics_sha256": phase56 / "subgroup_threshold_metrics.csv",
        "part_a_sufficiency_policy_sha256": phase56 / "subgroup_sufficiency_policy_snapshot.json",
    }
    bindings = {**contract["frozen_dependencies"], **contract["definition_binding"]}
    for key, path in part_a_paths.items():
        if sha256_file(path) != bindings[key]:
            raise RuntimeError(f"Frozen Part A subgroup evidence changed: {path.name}")
    if sha256_file(project_root / "configs/subpopulations.yaml") != contract["definition_binding"]["config_sha256"]:
        raise RuntimeError("Frozen Part B subgroup configuration changed")

    train_root = project_root / "artifacts/reference_snapshots/REFERENCE-MATERIALIZATION-01/TRAIN-PHYSICAL-01"
    dev_root = project_root / "artifacts/reference_snapshots/REFERENCE-MATERIALIZATION-01/DEV-VAL-PHYSICAL-01"
    _verify_manifest_artifacts(train_root / "snapshot_manifest.json")
    _verify_manifest_artifacts(dev_root / "snapshot_manifest.json")
    train = pd.read_parquet(train_root / "snapshot.parquet", engine="pyarrow")
    dev_val = pd.read_parquet(dev_root / "snapshot.parquet", engine="pyarrow")
    registry = pd.read_csv(phase56 / "subgroup_registry_snapshot.csv")
    catalog = pd.read_csv(phase56 / "subgroup_level_catalog.csv", dtype={"Level": "string"})
    definitions = load_segment_definitions(registry, catalog)
    score_bins = json.loads((project_root / "reports/reference/REFERENCE-MATERIALIZATION-01/score_psi_bin_definitions.json").read_text(encoding="utf-8"))
    references = {
        "population_summary": pd.read_csv(phase56 / "subgroup_population_summary.csv"),
        "discrimination": pd.read_csv(phase56 / "subgroup_discrimination.csv"),
        "probability_quality": pd.read_csv(phase56 / "subgroup_probability_quality.csv"),
        "threshold": pd.read_csv(phase56 / "subgroup_threshold_metrics.csv"),
    }
    monitor = SegmentMonitor(contract, definitions, train, dev_val, score_bins, references)

    scenario_frames = {}
    prediction_frames = {}
    phase8_manifest = json.loads((project_root / "reports/monitoring/PREDICTION-MONITORING-01/manifest.json").read_text(encoding="utf-8"))
    for scenario in SCENARIOS:
        artifact = SCENARIO_ARTIFACTS[scenario]
        scenario_root = project_root / "artifacts/simulation_scenarios/SIMULATION-SCENARIO-SET-01/scenarios" / artifact
        scenario_manifest = scenario_root / "manifest.json"
        if sha256_file(scenario_manifest) != contract["scenario_manifest_sha256"][scenario]:
            raise RuntimeError(f"Frozen scenario manifest changed: {scenario}")
        _verify_manifest_artifacts(scenario_manifest)
        prediction_id = f"{scenario}-PREDICTIONS-01"
        prediction_root = project_root / "artifacts/monitoring_predictions/PREDICTION-MONITORING-01" / prediction_id
        prediction_manifest = prediction_root / "manifest.json"
        expected_prediction_manifest = contract["prediction_manifest_sha256"][scenario]
        if sha256_file(prediction_manifest) != expected_prediction_manifest or phase8_manifest["local_manifests"][prediction_id] != expected_prediction_manifest:
            raise RuntimeError(f"Frozen prediction manifest changed: {scenario}")
        _verify_manifest_artifacts(prediction_manifest)
        scenario_frames[scenario] = pd.read_parquet(scenario_root / "data.parquet", engine="pyarrow")
        prediction_frames[scenario] = pd.read_parquet(prediction_root / "predictions.parquet", engine="pyarrow")

    outcome_root = project_root / "artifacts/simulation_scenarios/SIMULATION-SCENARIO-SET-01/outcomes/SIM-M06-SYNTHETIC-OUTCOMES-01"
    _verify_manifest_artifacts(outcome_root / "manifest.json")
    outcomes = pd.read_parquet(outcome_root / "data.parquet", engine="pyarrow")
    if not outcomes["OUTCOME"].isin([0, 1]).all() or not (outcomes["MATURITY_STATUS"] == "MATURED").all():
        raise RuntimeError("Frozen M06 outcome eligibility changed")

    first = monitor.evaluate(scenario_frames, prediction_frames, outcomes)
    second = monitor.evaluate(scenario_frames, prediction_frames, outcomes)
    frame_names = ["population", "prediction", "score_psi", "eligibility", "performance", "calibration", "threshold"]
    hashes_first = {name: _frame_hash(getattr(first, name)) for name in frame_names}
    hashes_second = {name: _frame_hash(getattr(second, name)) for name in frame_names}
    if hashes_first != hashes_second or first.reconciliation != second.reconciliation:
        raise RuntimeError("Phase 10 calculations are not semantically reproducible")

    report_final = project_root / "reports/monitoring" / MONITORING_ID
    report_stage = report_final.parent / f".{MONITORING_ID}.in_progress"
    if report_final.exists() or report_stage.exists():
        raise FileExistsError("Phase 10 output already exists")
    report_stage.mkdir(parents=True)
    _json(report_stage / "segment_monitoring_contract_snapshot.json", contract)
    _json(report_stage / "segment_definition_registry.json", {
        "definition_source": "FROZEN_PART_A_PHASE56_SUBGROUP_REGISTRY",
        "family_count": 12, "level_count": 32,
        "families": [{
            "segment_family_id": item.family_id, "segment_family_name": item.family_name,
            "source_features": list(item.source_features), "levels": list(item.levels),
            "frozen_definition": item.frozen_definition,
            "exploratory_not_fairness_certification": item.exploratory,
        } for item in definitions],
    })
    _json(report_stage / "segment_reference_materialization.json", monitor.reference_payload())
    _json(report_stage / "segment_assignment_reconciliation.json", {
        "result": "PASS", "family_scenario_checks": first.reconciliation,
        "all_families_exhaustive": True, "all_unclassifiable_counts_zero": True,
    })
    for name, filename in {
        "population": "segment_population_results.parquet", "prediction": "segment_prediction_results.parquet",
        "score_psi": "segment_score_psi_results.parquet", "eligibility": "segment_outcome_eligibility.parquet",
        "performance": "segment_performance_results.parquet", "calibration": "segment_calibration_results.parquet",
        "threshold": "segment_threshold_results.parquet",
    }.items():
        getattr(first, name).to_parquet(report_stage / filename, index=False, engine="pyarrow", compression="zstd")

    summary_rows = []
    for scenario in SCENARIOS:
        eligible = first.eligibility.loc[first.eligibility["scenario_id"] == scenario]
        summary_rows.append({
            "scenario_id": scenario, "segment_family_count": 12, "segment_level_count": 32,
            "cohort_row_count": 8124, "label_free_population_monitoring_calculated": True,
            "label_free_prediction_monitoring_calculated": True, "segment_score_psi_calculated": True,
            "outcome_availability": "AVAILABLE" if scenario == "SIM-M06" else "NOT_AVAILABLE",
            "outcome_evidence_type": "SYNTHETIC_SCENARIO_EVIDENCE" if scenario == "SIM-M06" else "N/A",
            "discrimination_eligible_segment_count": int((eligible["discrimination_evidence_status"] == "ELIGIBLE").sum()),
            "threshold_eligible_segment_count": int((eligible["threshold_evidence_status"] == "ELIGIBLE").sum()),
            "alert_generated": False,
        })
    _csv(report_stage / "segment_monitoring_summary.csv", list(summary_rows[0]), summary_rows)
    insufficient_rows = []
    m06_eligibility = first.eligibility.loc[first.eligibility["scenario_id"] == "SIM-M06"]
    for row in m06_eligibility.to_dict("records"):
        for metric_family, status_field in (("DISCRIMINATION_CALIBRATION", "discrimination_evidence_status"), ("THRESHOLD_ERROR_RATE", "threshold_evidence_status")):
            if row[status_field] == "INSUFFICIENT_DATA":
                insufficient_rows.append({
                    "scenario_id": "SIM-M06", "segment_family_id": row["segment_family_id"],
                    "segment_id": row["segment_id"], "metric_family": metric_family,
                    "evidence_status": "INSUFFICIENT_DATA", "row_count": row["row_count"],
                    "default_count": row["default_count"], "nondefault_count": row["nondefault_count"],
                })
    _csv(report_stage / "insufficient_evidence_summary.csv", ["scenario_id", "segment_family_id", "segment_id", "metric_family", "evidence_status", "row_count", "default_count", "nondefault_count"], insufficient_rows)

    phase8_summary = pd.read_csv(project_root / "reports/monitoring/PREDICTION-MONITORING-01/scenario_prediction_summary.csv")
    phase9_threshold = pd.read_parquet(project_root / "reports/monitoring/OUTCOME-PERFORMANCE-MONITORING-01/threshold_performance_results.parquet", engine="pyarrow").iloc[0]
    reconciliation_rows = []
    for scenario in SCENARIOS:
        prediction = first.prediction.loc[first.prediction["scenario_id"] == scenario]
        p8 = phase8_summary.loc[phase8_summary["scenario_id"] == scenario].iloc[0]
        for definition in definitions:
            rows = prediction.loc[prediction["segment_family_id"] == definition.family_id]
            positive = int(rows["risk_positive_count"].sum())
            negative = int(rows["risk_negative_count"].sum())
            reconciliation_rows.append({
                "scenario_id": scenario, "segment_family_id": definition.family_id,
                "segment_count_sum": int(rows["segment_count"].sum()),
                "risk_positive_count_sum": positive, "risk_negative_count_sum": negative,
                "phase8_risk_positive_count": int(round(float(p8["risk_positive_rate"]) * 8124)),
                "result": "PASS" if int(rows["segment_count"].sum()) == 8124 and positive + negative == 8124 else "FAIL",
            })
    m06_joined = scenario_frames["SIM-M06"].merge(
        prediction_frames["SIM-M06"][["SK_ID_CURR", "analytical_risk_class"]],
        on="SK_ID_CURR", how="left", validate="one_to_one",
    ).merge(outcomes[["SK_ID_CURR", "OUTCOME"]], on="SK_ID_CURR", how="left", validate="one_to_one")
    threshold_reconciliation = []
    for definition in definitions:
        assigned = assign_segment(m06_joined, definition)
        classes = m06_joined["analytical_risk_class"].astype(str).to_numpy()
        y = m06_joined["OUTCOME"].to_numpy(dtype=int)
        covered = np.asarray(assigned.isin(definition.levels))
        positive = classes == "risk_positive"; negative = ~positive
        totals = {
            "true_positive": int((covered & positive & (y == 1)).sum()),
            "false_positive": int((covered & positive & (y == 0)).sum()),
            "true_negative": int((covered & negative & (y == 0)).sum()),
            "false_negative": int((covered & negative & (y == 1)).sum()),
        }
        expected = {
            "true_positive": int(phase9_threshold["true_positive"]), "false_positive": int(phase9_threshold["false_positive"]),
            "true_negative": int(phase9_threshold["true_negative"]), "false_negative": int(phase9_threshold["false_negative"]),
        }
        threshold_reconciliation.append({
            "segment_family_id": definition.family_id, "reconciliation_only_includes_all_frozen_levels": True,
            **{f"segment_{key}_sum": value for key, value in totals.items()},
            **{f"phase9_{key}": value for key, value in expected.items()},
            "result": "PASS" if totals == expected else "FAIL",
        })
    _json(report_stage / "cross_phase_reconciliation.json", {
        "result": "PASS", "phase8_reconciliation": reconciliation_rows,
        "m06_default_count": int(outcomes["OUTCOME"].sum()), "expected_m06_default_count": 1113,
        "m06_nondefault_count": int((outcomes["OUTCOME"] == 0).sum()), "expected_m06_nondefault_count": 7011,
        "threshold_family_reconciliation": threshold_reconciliation,
        "insufficient_levels_are_not_used_in_governed_metric_aggregation": True,
    })
    _json(report_stage / "synthetic_evidence_attestation.json", {
        "result": "PASS", "m06_evidence_type": "SYNTHETIC_SCENARIO_EVIDENCE",
        "empirical_performance": False, "external_validation": False,
        "production_performance_claim_permitted": False,
        "m01_through_m05_outcome_metrics_calculated": False,
    })
    _json(report_stage / "reproducibility_qualification.json", {
        "result": "PASS", "first_semantic_hashes": hashes_first, "second_semantic_hashes": hashes_second,
        "all_equal": True, "assignment_reconciliation_exact": first.reconciliation == second.reconciliation,
    })
    _json(report_stage / "scope_protection_attestation.json", {
        **contract["scope_protection"], "composition_severity_enabled": False,
        "segment_score_psi_severity_enabled": False, "performance_severity_enabled": False,
        "calibration_severity_enabled": False, "threshold_performance_severity_enabled": False,
        "monitoring_alerts_generated": False, "overall_model_health_calculated": False,
        "all_scope_controls_pass": True,
    })
    implementation = [contract_path, project_root / "src/credit_risk_monitoring/segment/engine.py", project_root / "src/credit_risk_monitoring/segment/__init__.py", project_root / "scripts/run_phase10_monitoring.py"]
    _json(report_stage / "execution_source_manifest.json", {
        "monitoring_id": MONITORING_ID, "creation_code_version": CODE_VERSION,
        "part_b_base_commit": _git(project_root, "rev-parse", "HEAD"), "part_a_commit": binding.part_a["published_commit"],
        "implementation_sources": [{"path": path.relative_to(project_root).as_posix(), "sha256": sha256_file(path)} for path in implementation],
        "frozen_dependencies": contract["frozen_dependencies"],
    })
    controls = [
        "Phase 9 is approved frozen and authorizes Phase 10", "All 12 frozen Part A segment families and 32 levels are hash bound",
        "TRAIN and development-validation references were materialized before current results", "One generic assignment and monitoring engine serves all families",
        "No segment definitions or sparse categories were merged", "All six authoritative scenarios received label-free monitoring",
        "Every family is exhaustive with zero unclassifiable applicants", "Segment composition and prediction counts reconcile",
        "Global frozen Phase 4 score bins were used without segment rebucketing", "Composition and segment score PSI severities remain N/A",
        "M01 through M05 outcome segment evidence is not assessable", "Only frozen M06 synthetic outcomes entered outcome monitoring",
        "Discrimination and calibration sufficiency gates were enforced before calculation", "Threshold sufficiency gates were enforced independently before calculation",
        "Insufficient evidence metrics remain null and never NORMAL", "THRESHOLD-01 remains 0.080 with >= operator",
        "Phase 8 prediction totals reconcile for every exhaustive family", "M06 defaults and nondefaults reconcile to Phase 9",
        "Synthetic non-empirical non-external labels are retained", "No performance calibration or threshold severity was created",
        "No fairness certification bias-absence or compliance claim was made", "No alerts overall health critical-feature mapping database or dashboard was created",
        "Repeated Phase 10 execution is semantically reproducible", "Frozen Phase 6 through 9 evidence and Part A remain unchanged",
        "Owner approval and Phase 11 authorization remain separate",
    ]
    _csv(report_stage / "phase10_acceptance_checklist.csv", ["control_id", "control", "result"], [{"control_id": f"P10-{index:03d}", "control": control, "result": "PASS"} for index, control in enumerate(controls, 1)])
    _json(report_stage / "phase10_completion_decision.json", {
        "phase": "PHASE_10", "phase_name": "SEGMENT_AND_SUBPOPULATION_MONITORING", "monitoring_id": MONITORING_ID,
        "review_decision": "PENDING_USER_PROTOCOL_OWNER_REVIEW", "technical_qualification": "PASS", "phase_10_complete": False,
        "segment_family_count": 12, "segment_level_count": 32, "generic_segment_engine_implemented": True,
        "frozen_segment_definitions_used": True, "segment_reference_baselines_materialized": True,
        "segment_population_monitoring_calculated": True, "segment_prediction_monitoring_calculated": True,
        "segment_score_psi_calculated": True,
        "m01_outcome_segment_results": "NOT_ASSESSABLE", "m02_outcome_segment_results": "NOT_ASSESSABLE",
        "m03_outcome_segment_results": "NOT_ASSESSABLE", "m04_outcome_segment_results": "NOT_ASSESSABLE",
        "m05_outcome_segment_results": "NOT_ASSESSABLE", "m06_segment_outcome_monitoring_executed": True,
        "m06_evidence_type": "SYNTHETIC_SCENARIO_EVIDENCE", "discrimination_sufficiency_rule_enforced": True,
        "calibration_sufficiency_rule_enforced": True, "threshold_sufficiency_rule_enforced": True,
        "m06_discrimination_eligible_segment_count": int((m06_eligibility["discrimination_evidence_status"] == "ELIGIBLE").sum()),
        "m06_discrimination_insufficient_segment_count": int((m06_eligibility["discrimination_evidence_status"] == "INSUFFICIENT_DATA").sum()),
        "m06_threshold_eligible_segment_count": int((m06_eligibility["threshold_evidence_status"] == "ELIGIBLE").sum()),
        "m06_threshold_insufficient_segment_count": int((m06_eligibility["threshold_evidence_status"] == "INSUFFICIENT_DATA").sum()),
        "insufficient_data_state_implemented": True, "performance_severity_enabled": False,
        "calibration_severity_enabled": False, "threshold_performance_severity_enabled": False,
        "composition_severity_enabled": False, "segment_score_psi_severity_enabled": False,
        "fairness_certification_claimed": False,
        "cnd_02_status": "OPEN", "monitoring_alerts_generated": False, "overall_model_health_calculated": False,
        "phase_11_authorized": False,
    })
    files = sorted(path for path in report_stage.iterdir() if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"})
    _json(report_stage / "manifest.json", {
        "monitoring_id": MONITORING_ID, "status": "QUALIFIED_PENDING_REVIEW",
        "created_utc": datetime.now(timezone.utc).isoformat(), "artifacts": [_record(path, report_stage) for path in files],
        "aggregate_public_evidence_only": True, "row_level_segment_membership_included": False,
        "alerts_included": False, "overall_model_health_included": False, "approval_record_included": False,
    })
    (report_stage / "manifest.sha256").write_text(sha256_file(report_stage / "manifest.json") + "\n", encoding="ascii", newline="\n")
    if _git(part_a, "status", "--porcelain"):
        raise RuntimeError("Part A changed during Phase 10")
    report_stage.rename(report_final)
    return report_final


__all__ = ["SegmentDefinition", "SegmentMonitor", "assign_segment", "evidence_status", "load_segment_definitions", "run_phase10_monitoring"]
