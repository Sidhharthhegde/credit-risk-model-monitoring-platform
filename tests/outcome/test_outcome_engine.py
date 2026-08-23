from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve

from credit_risk_monitoring.outcome.engine import OutcomePerformanceMonitor, reconcile_prediction_outcomes


def _contract() -> dict:
    return {
        "threshold": {"value": 0.08},
        "calculation_policy": {"log_loss_probability_clip_epsilon": 1e-15},
    }


def _band_reference() -> pd.DataFrame:
    rows = []
    edges = [0.1 * index for index in range(1, 11)]
    for index, upper in enumerate(edges, 1):
        rows.append({
            "Bin_ID": index,
            "Interval_Notation": f"band-{index}",
            "Upper_Boundary": upper,
            "Applicant_Count": 10,
            "Mean_Predicted_Probability": upper - 0.05,
            "Observed_Default_Rate": upper - 0.05,
        })
    return pd.DataFrame(rows)


def _monitor() -> OutcomePerformanceMonitor:
    performance = {"roc_auc": 0.75, "ks": 0.5, "pr_auc_average_precision": 0.5, "gini": 0.5}
    calibration = {
        "observed_default_rate": 0.5,
        "mean_raw_probability": 0.5,
        "observed_expected_ratio": 1.0,
        "brier_score": 0.25,
        "log_loss": 0.6931471805599453,
    }
    threshold = {
        "true_positive": 1,
        "false_positive": 1,
        "true_negative": 1,
        "false_negative": 1,
        "default_capture_recall": 0.5,
        "specificity": 0.5,
        "precision": 0.5,
        "risk_negative_default_rate": 0.5,
    }
    return OutcomePerformanceMonitor(_contract(), performance, calibration, _band_reference(), threshold)


def _joined() -> pd.DataFrame:
    return pd.DataFrame({
        "SK_ID_CURR": [1, 2, 3, 4],
        "raw_probability": [0.01, 0.08, 0.4, 0.9],
        "analytical_risk_class": ["risk_negative", "risk_positive", "risk_positive", "risk_positive"],
        "OUTCOME": [0, 0, 1, 1],
    })


def test_identity_reconciliation_requires_exact_unique_complete_sets() -> None:
    predictions = _joined().drop(columns="OUTCOME")
    outcomes = _joined()[["SK_ID_CURR", "OUTCOME"]]
    assert len(reconcile_prediction_outcomes(predictions, outcomes)) == 4

    with pytest.raises(ValueError, match="differ"):
        reconcile_prediction_outcomes(predictions, outcomes.assign(SK_ID_CURR=[1, 2, 3, 5]))
    with pytest.raises(ValueError, match="duplicated"):
        reconcile_prediction_outcomes(predictions, outcomes.assign(SK_ID_CURR=[1, 1, 3, 4]))
    with pytest.raises(ValueError, match="binary"):
        reconcile_prediction_outcomes(predictions, outcomes.assign(OUTCOME=[0, 0, 1, 2]))


def test_discrimination_metrics_match_controlled_definitions() -> None:
    joined = _joined()
    result = _monitor().evaluate(joined)
    y = joined["OUTCOME"].to_numpy()
    p = joined["raw_probability"].to_numpy()
    fpr, tpr, _ = roc_curve(y, p)
    assert result.performance["roc_auc"] == pytest.approx(roc_auc_score(y, p))
    assert result.performance["performance_ks"] == pytest.approx(np.max(tpr - fpr))
    assert result.performance["pr_auc_average_precision"] == pytest.approx(average_precision_score(y, p))
    assert result.performance["gini"] == pytest.approx(2 * result.performance["roc_auc"] - 1)


def test_calibration_and_frozen_band_results_reconcile() -> None:
    result = _monitor().evaluate(_joined())
    assert result.calibration["synthetic_observed_default_count"] == 2
    assert result.calibration["synthetic_observed_default_rate"] == pytest.approx(0.5)
    assert result.calibration["average_raw_probability"] == pytest.approx(0.3475)
    assert result.calibration["observed_expected_ratio"] == pytest.approx(2 / 1.39)
    assert result.calibration_bands["row_count"].sum() == 4
    assert result.calibration_bands["synthetic_observed_default_count"].sum() == 2
    assert result.calibration["calibration_slope"] is None
    assert result.calibration["calibration_intercept"] is None


def test_threshold_boundary_and_confusion_matrix_use_frozen_policy() -> None:
    result = _monitor().evaluate(_joined())
    threshold = result.threshold_performance
    assert threshold["threshold_value"] == 0.08
    assert threshold["threshold_operator"] == ">="
    assert threshold["true_positive"] == 2
    assert threshold["false_positive"] == 1
    assert threshold["true_negative"] == 1
    assert threshold["false_negative"] == 0


def test_synthetic_results_never_generate_performance_alerts() -> None:
    result = _monitor().evaluate(_joined())
    assert result.performance["performance_severity"] == "N/A"
    assert result.calibration["calibration_severity"] == "N/A"
    assert result.threshold_performance["threshold_performance_severity"] == "N/A"
    assert not result.performance["alert_generated"]
    assert not result.calibration["alert_generated"]
    assert not result.threshold_performance["alert_generated"]
    assert not result.performance["empirical_performance"]
    assert not result.performance["external_validation"]


def test_invalid_probabilities_and_single_class_outcomes_are_rejected() -> None:
    for bad in (np.nan, np.inf, -0.01, 1.01):
        joined = _joined()
        joined.loc[0, "raw_probability"] = bad
        with pytest.raises(ValueError, match="probabilities"):
            _monitor().evaluate(joined)
    with pytest.raises(ValueError, match="Both outcome classes"):
        _monitor().evaluate(_joined().assign(OUTCOME=0))


def test_phase9_final_decision_records_independent_taxonomy_when_present() -> None:
    root = Path(__file__).resolve().parents[2]
    report = root / "reports/monitoring/OUTCOME-PERFORMANCE-MONITORING-01"
    if report.exists():
        decision = json.loads((report / "phase9_completion_decision.json").read_text(encoding="utf-8"))
        assert decision["review_decision"] == "APPROVED"
        assert decision["phase_9_complete"] is True
        assert decision["phase_10_authorized"] is True
        assert decision["m01_performance_status"] == "NOT_ASSESSABLE"
        assert decision["m06_outcome_availability"] == "AVAILABLE"
        assert decision["m06_maturity_status"] == "MATURED"
        assert decision["m06_evidence_status"] == "ELIGIBLE"
        assert decision["m06_outcome_evidence_type"] == "SYNTHETIC_SCENARIO_EVIDENCE"
        eligibility = json.loads((report / "evidence_eligibility_results.json").read_text(encoding="utf-8"))["results"]
        m01 = next(row for row in eligibility if row["scenario_id"] == "SIM-M01")
        m06 = next(row for row in eligibility if row["scenario_id"] == "SIM-M06")
        assert m01["evidence_status"] == "NOT_ASSESSABLE"
        assert m01["non_assessability_reason"] == "OUTCOME_NOT_AVAILABLE"
        assert m06["evidence_status"] == "ELIGIBLE"
        assert m06["non_assessability_reason"] is None
