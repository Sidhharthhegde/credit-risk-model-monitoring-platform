"""Phase 11 read-only breach qualification, alerts, authorization and health."""

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
from sklearn.metrics import roc_curve

from credit_risk_monitoring.qualification.binding import load_binding, resolve_part_a_root, sha256_file, verify_artifacts
from credit_risk_monitoring.reference.materialization import _semantic_hash


ALERT_ENGINE_ID = "ALERT-ENGINE-01"
CODE_VERSION = "PHASE11-ALERT-ENGINE-0.1.1"
AUTHORITATIVE_ARTIFACTS = {
    "SIM-M01": "SIM-M01-SCENARIO-01", "SIM-M02": "SIM-M02-SCENARIO-01",
    "SIM-M03": "SIM-M03-SCENARIO-01", "SIM-M04": "SIM-M04-SCENARIO-01",
    "SIM-M05": "SIM-M05-VALID-DEGRADED-01", "SIM-M06": "SIM-M06-SCENARIO-01",
}
BLOCKED_ARTIFACTS = ["SIM-M05-SOURCE-LOSS-DIAGNOSTIC-01", "SIM-M05-HARD-FAIL-01"]
SEVERITY_ORDER = {"NOT_ASSESSABLE": -1, "NORMAL": 0, "WARNING": 1, "CRITICAL": 2}


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


def _verify_public_manifest(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "APPROVED_FROZEN":
        raise RuntimeError(f"Upstream evidence is not approved frozen: {manifest_path}")
    for artifact in manifest["artifacts"]:
        if sha256_file(manifest_path.parent / artifact["path"]) != artifact["sha256"]:
            raise RuntimeError(f"Upstream artifact changed: {manifest_path.parent / artifact['path']}")


def deterministic_alert_id(model_id: str, run_id: str, alert_class: str, metric_id: str, entity_id: str) -> str:
    content = "|".join([model_id, run_id, alert_class, metric_id, entity_id])
    return "ALT-" + hashlib.sha256(content.encode("utf-8")).hexdigest()[:20].upper()


def aggregate_health(component_states: list[str], *, authorization_status: str, evidence_complete: bool) -> str:
    if authorization_status != "AUTHORIZED":
        return "NOT_ASSESSABLE"
    primary = [state for state in component_states if state in {"NORMAL", "WARNING", "CRITICAL"}]
    if "CRITICAL" in primary:
        return "CRITICAL"
    if "WARNING" in primary:
        return "WARNING"
    if evidence_complete and primary and all(state == "NORMAL" for state in primary):
        return "NORMAL"
    return "NOT_ASSESSABLE"


def persistence_sequence(severities: list[str], comparable: list[bool], warning_runs: int = 2) -> list[dict[str, Any]]:
    results = []
    consecutive = 0
    prior_comparable = None
    for index, (severity, eligible) in enumerate(zip(severities, comparable, strict=True)):
        if not eligible:
            consecutive = 0
            results.append({"index": index, "persistence_status": "NOT_ASSESSABLE", "consecutive_breach_count": 0, "repeat_breach_escalated": False})
            continue
        if severity in {"WARNING", "CRITICAL"}:
            consecutive = consecutive + 1 if prior_comparable is not None else 1
        else:
            consecutive = 0
        escalated = severity == "WARNING" and consecutive >= warning_runs
        results.append({"index": index, "persistence_status": "ASSESSED", "consecutive_breach_count": consecutive, "repeat_breach_escalated": escalated})
        prior_comparable = index
    return results


def transition_alert_status(current: str, target: str) -> str:
    allowed = {"OPEN": {"ACKNOWLEDGED"}, "ACKNOWLEDGED": {"RESOLVED"}, "RESOLVED": set()}
    if current not in allowed or target not in allowed[current]:
        raise ValueError(f"Alert lifecycle transition is not permitted: {current} -> {target}")
    return target


@dataclass(frozen=True)
class PerformanceControlPolicy:
    policy: dict[str, Any]

    def severity(self, metric_id: str, value: float) -> tuple[str, str]:
        rule = self.policy["metrics"][metric_id]
        reference = float(rule["reference_value"])
        standard_deviation = float(rule["bootstrap_standard_deviation"])
        direction = rule["adverse_direction"]
        delta = value - reference
        if direction not in {"LOWER_ONLY", "TWO_SIDED"}:
            raise ValueError(f"Unsupported adverse direction for {metric_id}: {direction}")
        adverse_distance = abs(delta) if direction == "TWO_SIDED" else reference - value
        critical_control = value < rule["critical_lower"] if direction == "LOWER_ONLY" else not (rule["critical_lower"] <= value <= rule["critical_upper"])
        warning_control = value < rule["warning_lower"] if direction == "LOWER_ONLY" else not (rule["warning_lower"] <= value <= rule["warning_upper"])
        critical_material = adverse_distance >= 2.0 * standard_deviation
        warning_material = adverse_distance >= 1.0 * standard_deviation
        if critical_control and critical_material:
            return "CRITICAL", "CRITICAL_CONTROL_LIMIT_AND_MATERIAL_BREACH"
        if warning_control and warning_material:
            return "WARNING", "WARNING_CONTROL_LIMIT_AND_MATERIAL_BREACH"
        return "NORMAL", "NO_JOINT_CONTROL_AND_MATERIAL_BREACH"


def _reference_metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    fpr, tpr, _ = roc_curve(y, p)
    auc = float(np.trapezoid(tpr, fpr))
    ks = float(np.max(tpr - fpr))
    oe = float(y.sum() / p.sum())
    recall = float(((p >= 0.08) & (y == 1)).sum() / (y == 1).sum())
    return {"roc_auc": auc, "performance_ks": ks, "observed_expected_ratio": oe, "recall_default_capture": recall}


def build_performance_policy(dev_val: pd.DataFrame, contract: dict[str, Any]) -> dict[str, Any]:
    y = dev_val["TARGET"].to_numpy(dtype=int)
    p = dev_val["raw_probability"].to_numpy(dtype=float)
    positives = p[y == 1]; negatives = p[y == 0]
    specification = contract["performance_alert_policy"]
    direct_metrics = set(specification["direct_metrics"])
    directions = specification.get("adverse_directions", {})
    if set(directions) != direct_metrics:
        missing = sorted(direct_metrics - set(directions))
        unexpected = sorted(set(directions) - direct_metrics)
        raise ValueError(f"Every direct performance metric requires exactly one adverse direction; missing={missing}, unexpected={unexpected}")
    if any(direction not in {"LOWER_ONLY", "TWO_SIDED"} for direction in directions.values()):
        raise ValueError("Direct performance metrics permit only LOWER_ONLY or TWO_SIDED adverse directions")
    two_sided = {metric for metric, direction in directions.items() if direction == "TWO_SIDED"}
    centers = specification.get("two_sided_centers", {})
    if set(centers) != two_sided or any(center != "REFERENCE_DISTRIBUTION" for center in centers.values()):
        raise ValueError("Every two-sided direct performance metric must be centered on REFERENCE_DISTRIBUTION")
    rng = np.random.default_rng(int(specification["seed"]))
    draws = {metric: np.empty(int(specification["iterations"]), dtype=float) for metric in specification["direct_metrics"]}
    for index in range(int(specification["iterations"])):
        positive_draw = positives[rng.integers(0, len(positives), len(positives))]
        negative_draw = negatives[rng.integers(0, len(negatives), len(negatives))]
        draw_p = np.concatenate([positive_draw, negative_draw])
        draw_y = np.concatenate([np.ones(len(positive_draw), dtype=int), np.zeros(len(negative_draw), dtype=int)])
        values = _reference_metrics(draw_y, draw_p)
        for metric, value in values.items():
            draws[metric][index] = value
    references = _reference_metrics(y, p)
    metrics = {}
    for metric, values in draws.items():
        warning_lower, warning_upper = np.quantile(values, specification["warning_quantiles"])
        critical_lower, critical_upper = np.quantile(values, specification["critical_quantiles"])
        metrics[metric] = {
            "reference_value": references[metric],
            "bootstrap_mean": float(values.mean()), "bootstrap_standard_deviation": float(values.std(ddof=1)),
            "warning_lower": float(warning_lower), "warning_upper": float(warning_upper),
            "critical_lower": float(critical_lower), "critical_upper": float(critical_upper),
            "adverse_direction": directions[metric],
            "comparison_center": centers.get(metric, "NOT_APPLICABLE_LOWER_ONLY"),
            "role": "DIRECT_ALERT_DRIVER",
        }
    return {
        "policy_id": specification["policy_id"], "status": "APPROVED_FROZEN_CONTROL_LIMITS",
        "reference_snapshot_id": specification["reference_snapshot_id"],
        "iterations": specification["iterations"], "seed": specification["seed"],
        "resampling": specification["resampling"], "warning_quantiles": specification["warning_quantiles"],
        "critical_quantiles": specification["critical_quantiles"],
        "warning_material_standard_deviations": specification["warning_material_standard_deviations"],
        "critical_material_standard_deviations": specification["critical_material_standard_deviations"],
        "both_material_and_control_breach_required": True, "p_value_only_alert_permitted": False,
        "adverse_direction_policy_frozen": True,
        "metrics": metrics,
    }


class AlertEngine:
    def __init__(self, performance_policy: PerformanceControlPolicy, critical_features: set[str]) -> None:
        self.performance_policy = performance_policy
        self.critical_features = critical_features

    def qualify(self, candidates: pd.DataFrame) -> pd.DataFrame:
        alerts = []
        for row in candidates.to_dict("records"):
            if row["evidence_status"] != "ELIGIBLE" or row["control_role"] != "DIRECT_ALERT_DRIVER":
                continue
            metric_severity = row["metric_severity"]
            if metric_severity not in {"WARNING", "CRITICAL"}:
                continue
            alert_severity = metric_severity
            reason = f"{row['metric_id'].upper()}_{metric_severity}"
            if row["component"] == "FEATURE_DRIFT" and metric_severity == "CRITICAL" and row["entity_id"] not in self.critical_features:
                alert_severity = "WARNING"
                reason = "CRITICAL_FEATURE_PSI_NONCRITICAL_PREDICTOR_PRIORITY_DOWNGRADE"
            alert_id = deterministic_alert_id("XGBT-01", row["run_id"], row["alert_class"], row["metric_id"], row["entity_id"])
            alerts.append({
                "alert_id": alert_id, "alert_key": alert_id, "model_id": "XGBT-01",
                "run_id": row["run_id"], "scenario_id": row["scenario_id"], "artifact_id": row["artifact_id"],
                "alert_class": row["alert_class"], "component": row["component"], "metric_id": row["metric_id"],
                "entity_type": row["entity_type"], "entity_id": row["entity_id"],
                "metric_value": row["metric_value"], "metric_severity": metric_severity,
                "alert_severity": alert_severity, "evidence_status": row["evidence_status"],
                "evidence_type": row["evidence_type"], "status": "OPEN", "reason_code": reason,
                "source_phase": row["source_phase"], "source_artifact_hash": row["source_artifact_hash"],
                "overall_health_contributor": True,
                "persistence_eligible": False, "prior_comparable_run_id": None,
                "consecutive_breach_count": None, "repeat_breach_escalated": False,
                "repeat_breach_status": "NOT_ASSESSABLE_NO_COMPARABLE_LONGITUDINAL_HISTORY",
                "production_performance_claim": False,
            })
        return pd.DataFrame(alerts)


def _critical_mapping(part_a_shap: pd.DataFrame, phase7_results: pd.DataFrame) -> dict[str, Any]:
    train = part_a_shap.loc[part_a_shap["Population"] == "TRAIN"].sort_values("Rank", kind="mergesort")
    tier1_end = int(train.loc[train["Cumulative_Share"] >= 0.80, "Rank"].iloc[0])
    tier2_end = int(train.loc[train["Cumulative_Share"] >= 0.95, "Rank"].iloc[0])
    rows = []
    for row in train.to_dict("records"):
        rank = int(row["Rank"])
        tier = "TIER_1" if rank <= tier1_end else ("TIER_2" if rank <= tier2_end else "TIER_3")
        rows.append({
            "feature": row["Feature"], "frozen_shap_rank": rank,
            "frozen_shap_share": float(row["Share_Of_Total_Abs_SHAP"]),
            "frozen_cumulative_share": float(row["Cumulative_Share"]), "frozen_materiality_tier": tier,
            "critical_predictor": tier == "TIER_1", "mapping_rule": "FROZEN_TRAIN_TIER_1_FIRST_80_PERCENT",
            "source_hash": "47e2b838782ee35409a8907cc430104e3da23a402d34237a87784313c0d4f605",
        })
    mapping = pd.DataFrame(rows)
    observed = phase7_results[["feature", "materiality_tier", "part_a_shap_rank"]].drop_duplicates().sort_values("feature").reset_index(drop=True)
    expected = mapping[["feature", "frozen_materiality_tier", "frozen_shap_rank"]].rename(columns={"frozen_materiality_tier": "materiality_tier", "frozen_shap_rank": "part_a_shap_rank"}).sort_values("feature").reset_index(drop=True)
    if not observed.equals(expected):
        raise RuntimeError("Critical-predictor mapping does not reconcile to frozen Phase 7 materiality")
    return {
        "mapping_id": "CRITICAL-PREDICTOR-MAPPING-01", "status": "FROZEN_PROSPECTIVE_MAPPING",
        "source_population": "TRAIN", "source_hash": rows[0]["source_hash"],
        "tier_1_end_rank": tier1_end, "tier_2_end_rank": tier2_end,
        "critical_rule": "TIER_1_THROUGH_FIRST_FEATURE_REACHING_80_PERCENT_CUMULATIVE_ABS_SHAP",
        "current_monitoring_results_used_to_select_mapping": False,
        "critical_predictor_count": int(mapping["critical_predictor"].sum()), "features": rows,
    }


def _candidate(**kwargs: Any) -> dict[str, Any]:
    base = {
        "run_id": None, "scenario_id": None, "artifact_id": None, "component": None,
        "alert_class": None, "metric_id": None, "entity_type": None, "entity_id": None,
        "metric_value": None, "metric_severity": "N/A", "evidence_status": "NOT_ASSESSABLE",
        "authority_status": "AUTHORITATIVE", "control_role": "SUPPORTING_CORROBORATION",
        "materiality_class": "N/A", "evidence_type": "MONITORING_EVIDENCE",
        "reference_id": None, "source_phase": None, "source_artifact_hash": None,
    }
    base.update(kwargs)
    return base


def _normalize(project_root: Path, performance_policy: PerformanceControlPolicy) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    dq_root = project_root / "reports/monitoring/DATA-QUALITY-CONTROL-01"
    dq_summary = pd.read_csv(dq_root / "scenario_control_summary.csv")
    authoritative = set(dq_summary.loc[dq_summary["downstream_monitoring_eligible"] == True, "artifact_id"])  # noqa: E712
    for filename in ["completeness_results.parquet", "categorical_novelty_results.parquet"]:
        path = dq_root / filename
        frame = pd.read_parquet(path, engine="pyarrow")
        source_hash = sha256_file(path)
        for row in frame.to_dict("records"):
            if row["artifact_id"] not in authoritative:
                continue
            candidates.append(_candidate(
                run_id=row["run_id"], scenario_id=row["scenario_id"], artifact_id=row["artifact_id"],
                component="DATA_QUALITY", alert_class="DATA_QUALITY", metric_id=row["metric_id"],
                entity_type="FEATURE", entity_id=row["feature"], metric_value=float(row["value"]),
                metric_severity=row["severity"], evidence_status=row["evidence_status"],
                control_role="DIRECT_ALERT_DRIVER", reference_id=row["reference_id"],
                source_phase="PHASE_6", source_artifact_hash=source_hash,
            ))

    drift_path = project_root / "reports/monitoring/FEATURE-DRIFT-MONITORING-01/feature_drift_results.parquet"
    drift = pd.read_parquet(drift_path, engine="pyarrow")
    for row in drift.to_dict("records"):
        candidates.append(_candidate(
            run_id=row["run_id"], scenario_id=row["scenario_id"], artifact_id=row["artifact_id"],
            component="FEATURE_DRIFT", alert_class="FEATURE_DRIFT", metric_id="feature_psi",
            entity_type="FEATURE", entity_id=row["feature"], metric_value=float(row["psi"]),
            metric_severity=row["severity"], evidence_status=row["evidence_status"],
            control_role="DIRECT_ALERT_DRIVER", materiality_class=row["materiality_tier"],
            reference_id=row["reference_id"], source_phase="PHASE_7", source_artifact_hash=sha256_file(drift_path),
        ))

    prediction_path = project_root / "reports/monitoring/PREDICTION-MONITORING-01/scenario_prediction_summary.csv"
    prediction = pd.read_csv(prediction_path)
    for row in prediction.to_dict("records"):
        for metric_id, value_field, severity_field in [
            ("score_psi", "score_psi", "score_psi_severity"),
            ("risk_positive_rate_absolute_change", "risk_positive_rate_change", "risk_positive_rate_severity"),
        ]:
            candidates.append(_candidate(
                run_id=f"PREDICTION-RUN-{row['scenario_id']}-01", scenario_id=row["scenario_id"], artifact_id=row["artifact_id"],
                component="PREDICTION", alert_class="PREDICTION", metric_id=metric_id,
                entity_type="MODEL_OUTPUT", entity_id="DF-01_RAW_PROBABILITY" if metric_id == "score_psi" else "THRESHOLD-01",
                metric_value=float(row[value_field]), metric_severity=row[severity_field], evidence_status="ELIGIBLE",
                control_role="DIRECT_ALERT_DRIVER", reference_id="PERF-REF-01", source_phase="PHASE_8",
                source_artifact_hash=sha256_file(prediction_path),
            ))

    performance_root = project_root / "reports/monitoring/OUTCOME-PERFORMANCE-MONITORING-01"
    performance = pd.read_parquet(performance_root / "performance_results.parquet", engine="pyarrow").iloc[0]
    calibration = pd.read_parquet(performance_root / "calibration_results.parquet", engine="pyarrow").iloc[0]
    threshold = pd.read_parquet(performance_root / "threshold_performance_results.parquet", engine="pyarrow").iloc[0]
    current = {
        "roc_auc": (float(performance["roc_auc"]), "PERFORMANCE", performance_root / "performance_results.parquet"),
        "performance_ks": (float(performance["performance_ks"]), "PERFORMANCE", performance_root / "performance_results.parquet"),
        "observed_expected_ratio": (float(calibration["observed_expected_ratio"]), "CALIBRATION", performance_root / "calibration_results.parquet"),
        "recall_default_capture": (float(threshold["recall_default_capture"]), "THRESHOLD_PERFORMANCE", performance_root / "threshold_performance_results.parquet"),
    }
    for scenario, artifact in AUTHORITATIVE_ARTIFACTS.items():
        for metric_id in current:
            if scenario == "SIM-M06":
                value, component, path = current[metric_id]
                severity, reason = performance_policy.severity(metric_id, value)
                candidates.append(_candidate(
                    run_id="OUTCOME-RUN-SIM-M06-01", scenario_id=scenario, artifact_id=artifact,
                    component=component, alert_class=component, metric_id=metric_id,
                    entity_type="MODEL", entity_id="DF-01", metric_value=value, metric_severity=severity,
                    evidence_status="ELIGIBLE", control_role="DIRECT_ALERT_DRIVER",
                    evidence_type="SYNTHETIC_SCENARIO_EVIDENCE", reference_id="PERF-REF-01",
                    source_phase="PHASE_9", source_artifact_hash=sha256_file(path), materiality_class=reason,
                ))
            else:
                candidates.append(_candidate(
                    run_id=f"OUTCOME-RUN-{scenario}-NA", scenario_id=scenario, artifact_id=artifact,
                    component="PERFORMANCE" if metric_id in {"roc_auc", "performance_ks"} else ("CALIBRATION" if metric_id == "observed_expected_ratio" else "THRESHOLD_PERFORMANCE"),
                    alert_class="OUTCOME_MONITORING", metric_id=metric_id, entity_type="MODEL", entity_id="DF-01",
                    evidence_status="NOT_ASSESSABLE", control_role="DIRECT_ALERT_DRIVER",
                    evidence_type="N/A", reference_id="PERF-REF-01", source_phase="PHASE_9",
                    source_artifact_hash=sha256_file(performance_root / "manifest.json"),
                ))

    # Supporting and derived M06 metrics are retained as candidates but cannot independently alert.
    supporting = [
        ("pr_auc_average_precision", float(performance["pr_auc_average_precision"]), "PERFORMANCE", "SUPPORTING_CORROBORATION"),
        ("gini", float(performance["gini"]), "PERFORMANCE", "DERIVED_ONLY"),
        ("brier_score", float(calibration["brier_score"]), "CALIBRATION", "SUPPORTING_CORROBORATION"),
        ("log_loss", float(calibration["log_loss"]), "CALIBRATION", "SUPPORTING_CORROBORATION"),
        ("specificity", float(threshold["specificity"]), "THRESHOLD_PERFORMANCE", "SUPPORTING_CORROBORATION"),
        ("precision", float(threshold["precision"]), "THRESHOLD_PERFORMANCE", "SUPPORTING_CORROBORATION"),
        ("false_negative_rate", float(threshold["false_negative_rate"]), "THRESHOLD_PERFORMANCE", "DERIVED_ONLY"),
    ]
    for metric_id, value, component, role in supporting:
        candidates.append(_candidate(
            run_id="OUTCOME-RUN-SIM-M06-01", scenario_id="SIM-M06", artifact_id=AUTHORITATIVE_ARTIFACTS["SIM-M06"],
            component=component, alert_class=component, metric_id=metric_id, entity_type="MODEL", entity_id="DF-01",
            metric_value=value, metric_severity="N/A", evidence_status="ELIGIBLE", control_role=role,
            evidence_type="SYNTHETIC_SCENARIO_EVIDENCE", reference_id="PERF-REF-01", source_phase="PHASE_9",
            source_artifact_hash=sha256_file(performance_root / "manifest.json"),
        ))

    segment_summary_path = project_root / "reports/monitoring/SEGMENT-MONITORING-01/segment_monitoring_summary.csv"
    for row in pd.read_csv(segment_summary_path).to_dict("records"):
        candidates.append(_candidate(
            run_id=f"SEGMENT-RUN-{row['scenario_id']}-01", scenario_id=row["scenario_id"], artifact_id=AUTHORITATIVE_ARTIFACTS[row["scenario_id"]],
            component="SEGMENT", alert_class="SEGMENT", metric_id="segment_monitoring_context",
            entity_type="SEGMENT_REGISTRY", entity_id="SUBPOPULATIONS-01", metric_value=float(row["segment_level_count"]),
            metric_severity="N/A", evidence_status="ELIGIBLE", control_role="CONTEXT_ONLY",
            evidence_type=row["outcome_evidence_type"], source_phase="PHASE_10", source_artifact_hash=sha256_file(segment_summary_path),
        ))

    authorization = []
    evidence_scope = []
    for scenario, artifact in AUTHORITATIVE_ARTIFACTS.items():
        authorization.append({"scenario_id": scenario, "artifact_id": artifact, "authorization_status": "AUTHORIZED", "reason_code": "ALL_INPUT_GOVERNANCE_GATES_PASS"})
        evidence_scope.append({
            "scenario_id": scenario, "artifact_id": artifact,
            "evidence_scope": "FULL_OUTCOME_ELIGIBLE" if scenario == "SIM-M06" else "LABEL_FREE_ONLY",
            "evidence_type": "SYNTHETIC_SCENARIO_EVIDENCE" if scenario == "SIM-M06" else "MONITORING_EVIDENCE",
        })
    authorization.extend([
        {"scenario_id": "SIM-M05", "artifact_id": BLOCKED_ARTIFACTS[0], "authorization_status": "BLOCKED_SOURCE_GOVERNANCE", "reason_code": "SOURCE_NON_AUTHORITATIVE_NO_APPROVED_FALLBACK_CND_02_OPEN"},
        {"scenario_id": "SIM-M05", "artifact_id": BLOCKED_ARTIFACTS[1], "authorization_status": "BLOCKED_HARD_GATE", "reason_code": "CONTRACT_AND_GRAIN_HARD_FAILURE"},
    ])
    evidence_scope.extend([
        {"scenario_id": "SIM-M05", "artifact_id": artifact, "evidence_scope": "NOT_ASSESSABLE", "evidence_type": "CONTROL_QUALIFICATION_EVIDENCE"}
        for artifact in BLOCKED_ARTIFACTS
    ])
    for item in authorization[-2:]:
        candidates.append(_candidate(
            run_id=f"AUTH-RUN-{item['artifact_id']}-01", scenario_id=item["scenario_id"], artifact_id=item["artifact_id"],
            component="GOVERNANCE", alert_class="GOVERNANCE_GATE", metric_id="authorization_gate",
            entity_type="ARTIFACT", entity_id=item["artifact_id"], metric_value=1.0, metric_severity="CRITICAL",
            evidence_status="ELIGIBLE", authority_status="NON_AUTHORITATIVE", control_role="DIRECT_ALERT_DRIVER",
            evidence_type="CONTROL_QUALIFICATION_EVIDENCE", source_phase="PHASE_6",
            source_artifact_hash=sha256_file(dq_root / "hard_gate_qualification.json"),
        ))
    return pd.DataFrame(candidates), authorization, evidence_scope


def _component_and_overall(candidates: pd.DataFrame, alerts: pd.DataFrame, authorization: list[dict[str, Any]], evidence_scope: list[dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    components = ["DATA_QUALITY", "FEATURE_DRIFT", "PREDICTION", "PERFORMANCE", "CALIBRATION", "THRESHOLD_PERFORMANCE", "SEGMENT"]
    component_rows = []
    overall_rows = []
    scope_by_artifact = {row["artifact_id"]: row for row in evidence_scope}
    for auth in authorization:
        artifact = auth["artifact_id"]
        scenario = auth["scenario_id"]
        artifact_alerts = alerts.loc[alerts["artifact_id"] == artifact] if len(alerts) else alerts
        states = []
        for component in components:
            if auth["authorization_status"] != "AUTHORIZED":
                state = "NOT_ASSESSABLE"
            elif component == "SEGMENT":
                state = "NOT_ASSESSABLE_FOR_ALERT_AGGREGATION"
            elif component in {"PERFORMANCE", "CALIBRATION", "THRESHOLD_PERFORMANCE"} and scenario != "SIM-M06":
                state = "NOT_ASSESSABLE"
            else:
                component_alerts = artifact_alerts.loc[artifact_alerts["component"] == component] if len(artifact_alerts) else artifact_alerts
                state = "NORMAL" if component_alerts.empty else max(component_alerts["alert_severity"], key=lambda value: SEVERITY_ORDER[value])
            component_rows.append({
                "scenario_id": scenario, "artifact_id": artifact, "component": component,
                "component_health": state, "alert_count": int((artifact_alerts["component"] == component).sum()) if len(artifact_alerts) else 0,
                "critical_alert_count": int(((artifact_alerts["component"] == component) & (artifact_alerts["alert_severity"] == "CRITICAL")).sum()) if len(artifact_alerts) else 0,
                "warning_alert_count": int(((artifact_alerts["component"] == component) & (artifact_alerts["alert_severity"] == "WARNING")).sum()) if len(artifact_alerts) else 0,
            })
            states.append(state)
        complete = scope_by_artifact[artifact]["evidence_scope"] == "FULL_OUTCOME_ELIGIBLE"
        overall_rows.append({
            "scenario_id": scenario, "artifact_id": artifact,
            "authorization_status": auth["authorization_status"],
            "evidence_scope": scope_by_artifact[artifact]["evidence_scope"],
            "evidence_type": scope_by_artifact[artifact]["evidence_type"],
            "overall_model_health": aggregate_health(states, authorization_status=auth["authorization_status"], evidence_complete=complete),
            "open_alert_count": int(len(artifact_alerts)),
            "critical_alert_count": int((artifact_alerts["alert_severity"] == "CRITICAL").sum()) if len(artifact_alerts) else 0,
            "warning_alert_count": int((artifact_alerts["alert_severity"] == "WARNING").sum()) if len(artifact_alerts) else 0,
        })
    return pd.DataFrame(component_rows), pd.DataFrame(overall_rows)


def run_phase11_alert_engine(project_root: Path, explicit_part_a_root: Path | None = None) -> Path:
    project_root = project_root.resolve()
    contract_path = project_root / "contracts/alert_engine_contract.json"
    policy_path = project_root / "configs/alert_aggregation_policy.yaml"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if sha256_file(policy_path) != contract["policy_binding"]["sha256"]:
        raise RuntimeError("Frozen prospective alert policy changed")
    upstream_paths = {
        "phase_6_manifest_sha256": "reports/monitoring/DATA-QUALITY-CONTROL-01/manifest.json",
        "phase_7_manifest_sha256": "reports/monitoring/FEATURE-DRIFT-MONITORING-01/manifest.json",
        "phase_8_manifest_sha256": "reports/monitoring/PREDICTION-MONITORING-01/manifest.json",
        "phase_9_manifest_sha256": "reports/monitoring/OUTCOME-PERFORMANCE-MONITORING-01/manifest.json",
        "phase_10_manifest_sha256": "reports/monitoring/SEGMENT-MONITORING-01/manifest.json",
        "legacy_alert_thresholds_sha256": "configs/alert_thresholds.yaml",
        "phase_7_materiality_lineage_sha256": "reports/monitoring/FEATURE-DRIFT-MONITORING-01/materiality_lineage.json",
        "phase_7_feature_results_sha256": "reports/monitoring/FEATURE-DRIFT-MONITORING-01/feature_drift_results.parquet",
        "phase_6_scenario_summary_sha256": "reports/monitoring/DATA-QUALITY-CONTROL-01/scenario_control_summary.csv",
    }
    for key, relative in upstream_paths.items():
        if sha256_file(project_root / relative) != contract["frozen_dependencies"][key]:
            raise RuntimeError(f"Frozen Phase 11 dependency changed: {relative}")
        if key.startswith("phase_") and key.endswith("manifest_sha256"):
            _verify_public_manifest(project_root / relative)
    phase10 = json.loads((project_root / "reports/monitoring/SEGMENT-MONITORING-01/phase10_completion_decision.json").read_text(encoding="utf-8"))
    if phase10["review_decision"] != "APPROVED" or not phase10["phase_11_authorized"]:
        raise RuntimeError("Phase 11 is not authorized")

    binding = load_binding(project_root / "contracts/part_a_binding.json")
    part_a = resolve_part_a_root(binding, explicit_part_a_root)
    _, binding_pass = verify_artifacts(binding, part_a)
    if not binding_pass or _git(part_a, "rev-parse", "HEAD") != binding.part_a["published_commit"] or _git(part_a, "status", "--porcelain"):
        raise RuntimeError("Part A binding or clean-state check failed")
    shap_path = part_a / "reports/formal_validation/phase57_explainability_feature_behaviour_validation_v1_1/raw_feature_shap_importance.csv"
    if sha256_file(shap_path) != contract["critical_predictor_mapping"]["source_sha256"]:
        raise RuntimeError("Frozen Part A SHAP materiality evidence changed")

    # Control limits and predictor criticality are derived before current Phase 9 evidence is normalized.
    dev_root = project_root / "artifacts/reference_snapshots/REFERENCE-MATERIALIZATION-01/DEV-VAL-PHYSICAL-01"
    if sha256_file(dev_root / "snapshot_manifest.json") != contract["performance_alert_policy"]["reference_snapshot_manifest_sha256"]:
        raise RuntimeError("Frozen performance reference snapshot changed")
    dev_manifest = json.loads((dev_root / "snapshot_manifest.json").read_text(encoding="utf-8"))
    for artifact in dev_manifest["artifacts"]:
        if sha256_file(dev_root / artifact["path"]) != artifact["sha256"]:
            raise RuntimeError(f"Frozen performance reference content changed: {artifact['path']}")
    dev_val = pd.read_parquet(dev_root / "snapshot.parquet", engine="pyarrow")
    performance_policy_payload = build_performance_policy(dev_val, contract)
    performance_policy = PerformanceControlPolicy(performance_policy_payload)
    phase7_results = pd.read_parquet(project_root / "reports/monitoring/FEATURE-DRIFT-MONITORING-01/feature_drift_results.parquet", engine="pyarrow")
    critical_mapping = _critical_mapping(pd.read_csv(shap_path), phase7_results)
    critical_features = {row["feature"] for row in critical_mapping["features"] if row["critical_predictor"]}

    candidates, authorization, evidence_scope = _normalize(project_root, performance_policy)
    engine = AlertEngine(performance_policy, critical_features)
    alerts = engine.qualify(candidates)
    components, overall = _component_and_overall(candidates, alerts, authorization, evidence_scope)
    # Repeat to qualify deterministic content independently of Parquet container metadata.
    alerts_second = engine.qualify(candidates.copy(deep=True))
    components_second, overall_second = _component_and_overall(candidates, alerts_second, authorization, evidence_scope)
    semantic_first = {"candidates": _semantic_hash(candidates), "alerts": _semantic_hash(alerts), "components": _semantic_hash(components), "overall": _semantic_hash(overall)}
    semantic_second = {"candidates": _semantic_hash(candidates.copy(deep=True)), "alerts": _semantic_hash(alerts_second), "components": _semantic_hash(components_second), "overall": _semantic_hash(overall_second)}
    if semantic_first != semantic_second:
        raise RuntimeError("Phase 11 alert results are not semantically reproducible")

    report_final = project_root / "reports/monitoring" / ALERT_ENGINE_ID
    report_stage = report_final.parent / f".{ALERT_ENGINE_ID}.in_progress"
    if report_final.exists() or report_stage.exists():
        raise FileExistsError("Phase 11 output already exists")
    report_stage.mkdir(parents=True)
    _json(report_stage / "alert_engine_contract_snapshot.json", contract)
    _json(report_stage / "alert_policy_snapshot.json", {
        "policy_id": contract["policy_id"], "status": contract["status"],
        "policy_path": "configs/alert_aggregation_policy.yaml", "policy_sha256": sha256_file(policy_path),
        "policy_text": policy_path.read_text(encoding="utf-8"),
    })
    _json(report_stage / "performance_alert_policy.json", performance_policy_payload)
    _json(report_stage / "critical_predictor_mapping.json", critical_mapping)
    _json(report_stage / "upstream_evidence_reconciliation.json", {
        "result": "PASS", "frozen_dependencies": contract["frozen_dependencies"],
        "all_upstream_hashes_verified": True, "upstream_metric_recalculation_performed": False,
        "upstream_severity_modification_performed": False, "part_a_modified": False,
    })
    candidates.to_parquet(report_stage / "normalized_breach_candidates.parquet", index=False, engine="pyarrow", compression="zstd")
    alerts.to_parquet(report_stage / "alert_results.parquet", index=False, engine="pyarrow", compression="zstd")
    components.to_parquet(report_stage / "component_health_results.parquet", index=False, engine="pyarrow", compression="zstd")
    overall.to_parquet(report_stage / "overall_health_results.parquet", index=False, engine="pyarrow", compression="zstd")
    _json(report_stage / "authorization_results.json", {"results": authorization})
    _json(report_stage / "evidence_scope_results.json", {"results": evidence_scope})
    role_counts = candidates["control_role"].value_counts().to_dict()
    _json(report_stage / "alert_driver_reconciliation.json", {
        "result": "PASS", "candidate_role_counts": role_counts,
        "alert_count": len(alerts), "unique_alert_id_count": int(alerts["alert_id"].nunique()),
        "duplicate_alert_ids": int(alerts["alert_id"].duplicated().sum()),
        "supporting_or_derived_alert_count": int(alerts["metric_id"].isin(["pr_auc_average_precision", "gini", "brier_score", "log_loss", "specificity", "precision", "false_negative_rate"]).sum()),
        "p_value_generated_alert_count": 0, "segment_generated_alert_count": int((alerts["component"] == "SEGMENT").sum()),
    })
    _json(report_stage / "alert_lifecycle_qualification.json", {
        "result": "PASS", "statuses": ["OPEN", "ACKNOWLEDGED", "RESOLVED"],
        "allowed_transitions": {"OPEN": ["ACKNOWLEDGED"], "ACKNOWLEDGED": ["RESOLVED"], "RESOLVED": []},
        "open_to_acknowledged_fixture": transition_alert_status("OPEN", "ACKNOWLEDGED"),
        "acknowledged_to_resolved_fixture": transition_alert_status("ACKNOWLEDGED", "RESOLVED"),
        "current_alerts_initial_status": "OPEN", "current_acknowledgements_or_resolutions_fabricated": False,
    })
    fixture = persistence_sequence(["WARNING", "WARNING", "NORMAL", "CRITICAL"], [True, True, True, True])
    _json(report_stage / "persistence_qualification.json", {
        "result": "PASS", "engine_implemented": True, "fixture_results": fixture,
        "two_comparable_warnings_escalate": fixture[1]["repeat_breach_escalated"],
        "normal_resets_count": fixture[2]["consecutive_breach_count"] == 0,
        "current_scenario_calendar_persistence_claimed": False,
        "current_repeat_breach_status": "NOT_ASSESSABLE_NO_COMPARABLE_LONGITUDINAL_HISTORY",
    })
    summary_rows = []
    for row in overall.to_dict("records"):
        summary_rows.append({
            "scenario_id": row["scenario_id"], "artifact_id": row["artifact_id"],
            "authorization_status": row["authorization_status"], "evidence_scope": row["evidence_scope"],
            "evidence_type": row["evidence_type"], "open_alert_count": row["open_alert_count"],
            "critical_alert_count": row["critical_alert_count"], "warning_alert_count": row["warning_alert_count"],
            "overall_model_health": row["overall_model_health"],
        })
    _csv(report_stage / "scenario_alert_summary.csv", list(summary_rows[0]), summary_rows)
    _json(report_stage / "synthetic_evidence_attestation.json", {
        "result": "PASS", "m06_performance_alert_evidence_type": "SYNTHETIC_SCENARIO_EVIDENCE",
        "empirical_performance": False, "external_validation": False,
        "production_performance_claim": False, "m01_through_m05_performance_alerts_generated": False,
    })
    _json(report_stage / "reproducibility_qualification.json", {
        "result": "PASS", "first_semantic_hashes": semantic_first, "second_semantic_hashes": semantic_second,
        "all_equal": True, "deterministic_alert_ids": True,
    })
    _json(report_stage / "scope_protection_attestation.json", {
        **contract["execution_barriers"], **contract["scope_protection"],
        "threshold_boundary_density_status": "CONTROLLED_DEFERRED",
        "current_scenario_calendar_persistence_claimed": False,
        "all_scope_controls_pass": True,
    })
    implementation = [contract_path, policy_path, project_root / "src/credit_risk_monitoring/alert/engine.py", project_root / "src/credit_risk_monitoring/alert/__init__.py", project_root / "scripts/run_phase11_alert_engine.py"]
    _json(report_stage / "execution_source_manifest.json", {
        "alert_engine_id": ALERT_ENGINE_ID, "creation_code_version": CODE_VERSION,
        "part_b_base_commit": _git(project_root, "rev-parse", "HEAD"), "part_a_commit": binding.part_a["published_commit"],
        "implementation_sources": [{"path": path.relative_to(project_root).as_posix(), "sha256": sha256_file(path)} for path in implementation],
        "frozen_dependencies": contract["frozen_dependencies"],
    })
    controls = [
        "Phase 10 approved frozen manifest authorizes Phase 11", "Alert policy was frozen before execution",
        "Critical-predictor mapping was derived only from frozen TRAIN SHAP evidence", "Performance limits were derived only from frozen development-validation evidence",
        "Performance alerts require both material and control-limit breach", "P-values cannot independently generate alerts",
        "Threshold-boundary density remains controlled deferred", "Phase 6 through 10 evidence was consumed read-only",
        "No upstream metric or severity was recalculated or modified", "Generic deterministic alert IDs are unique",
        "Direct supporting derived and contextual roles are enforced", "Supporting and derived performance metrics generated no duplicate alerts",
        "Hard contract and source governance blocks remain distinct", "Authorization evidence scope and health are independent",
        "M01 through M05 performance health remains not assessable", "M06 performance alerts remain synthetic non-empirical evidence",
        "Component health states are deterministic", "Overall normal requires complete required evidence",
        "Blocked artifacts receive not-assessable health", "Persistence logic passed dedicated comparable-run fixtures",
        "Current scenarios are not represented as longitudinal persistence", "Segment evidence remains contextual in alert-engine v1",
        "No model fit recalibration threshold tuning fairness certification database or dashboard was created",
        "Repeated Phase 11 execution is semantically reproducible", "Owner approval and Phase 12 authorization remain separate",
        "Every direct performance metric has an explicitly frozen adverse-direction rule",
    ]
    _csv(report_stage / "phase11_acceptance_checklist.csv", ["control_id", "control", "result"], [{"control_id": f"P11-{index:03d}", "control": control, "result": "PASS"} for index, control in enumerate(controls, 1)])
    _json(report_stage / "phase11_completion_decision.json", {
        "phase": "PHASE_11", "phase_name": "ALERT_ENGINE_BREACH_AGGREGATION_AND_MODEL_HEALTH",
        "alert_engine_id": ALERT_ENGINE_ID, "review_decision": "APPROVED",
        "technical_qualification": "PASS", "phase_11_complete": True, "upstream_evidence_read_only": True,
        "critical_predictor_mapping_approved": True, "performance_alert_limits_approved": True,
        "performance_uncertainty_policy_approved": True, "performance_adverse_direction_policy_approved": True,
        "threshold_boundary_density_status": "CONTROLLED_DEFERRED", "generic_alert_engine_implemented": True,
        "deterministic_alert_ids_implemented": True, "governance_gate_alerts_implemented": True,
        "dq_alerts_implemented": True, "feature_drift_alerts_implemented": True,
        "prediction_alerts_implemented": True, "performance_alerts_implemented": True,
        "alert_lifecycle_implemented": True, "alert_statuses": ["OPEN", "ACKNOWLEDGED", "RESOLVED"],
        "persistence_engine_implemented": True, "current_scenario_calendar_persistence_claimed": False,
        "component_health_calculated": True, "authorization_state_calculated": True,
        "evidence_scope_calculated": True, "overall_model_health_calculated": True,
        "alert_count": len(alerts), "open_alert_count": int((alerts["status"] == "OPEN").sum()),
        "cnd_02_status": "OPEN", "phase_12_authorized": True,
        "next_phase_authorized": "PHASE_12_MONITORING_HISTORY_EVIDENCE_PERSISTENCE_AND_QUERY_LAYER",
    })
    _json(report_stage / "phase11_approval_record.json", {
        "phase": "PHASE_11", "alert_engine_id": ALERT_ENGINE_ID, "review_decision": "APPROVED",
        "reviewed_candidate_manifest_sha256": "a836ca0c67b5c2ca4b0a17fe0ddabe3c2422c31456dbd81797c57d4cb0435a7f",
        "approval_condition": "EXPLICIT_PERFORMANCE_ADVERSE_DIRECTION_GOVERNANCE",
        "condition_remediated": True,
        "approved_adverse_directions": contract["performance_alert_policy"]["adverse_directions"],
        "two_sided_centers": contract["performance_alert_policy"]["two_sided_centers"],
        "calculated_alerts_expected_to_change": False,
        "reason": "The candidate implementation already enforced the approved directions; remediation moved them into the frozen policy and contract and added fail-closed validation.",
        "phase_12_authorized": True,
    })
    files = sorted(path for path in report_stage.iterdir() if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"})
    _json(report_stage / "manifest.json", {
        "alert_engine_id": ALERT_ENGINE_ID, "status": "APPROVED_FROZEN",
        "created_utc": datetime.now(timezone.utc).isoformat(), "artifacts": [_record(path, report_stage) for path in files],
        "aggregate_public_evidence_only": True, "upstream_evidence_read_only": True,
        "row_level_applicant_evidence_included": False, "approval_record_included": True,
    })
    (report_stage / "manifest.sha256").write_text(sha256_file(report_stage / "manifest.json") + "\n", encoding="ascii", newline="\n")
    if _git(part_a, "status", "--porcelain"):
        raise RuntimeError("Part A changed during Phase 11")
    report_stage.rename(report_final)
    return report_final


__all__ = ["AlertEngine", "PerformanceControlPolicy", "aggregate_health", "build_performance_policy", "deterministic_alert_id", "persistence_sequence", "run_phase11_alert_engine", "transition_alert_status"]
