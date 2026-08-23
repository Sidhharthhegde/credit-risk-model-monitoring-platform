from __future__ import annotations

import json
import inspect
from pathlib import Path

import numpy as np
import pandas as pd

from credit_risk_monitoring.prediction.engine import PredictionMonitor, _smooth, apply_threshold, run_phase8_monitoring


def _contract() -> dict:
    return {
        "threshold": {"threshold_id": "THRESHOLD-01", "value": 0.08, "operator": ">="},
        "score_reference": {"approved_quantiles": [0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]},
        "score_psi": {"control_id": "PR-SCORE-PSI-01", "metric_id": "PR-02", "epsilon": 1e-6, "warning": 0.1, "critical": 0.25},
        "threshold_output": {
            "control_id": "PR-RISK-POSITIVE-RATE-01", "metric_id": "PR-03",
            "absolute_rate_change_warning": 0.05, "absolute_rate_change_critical": 0.1,
            "terminology": "ANALYTICAL_DECISION_PROXY_NOT_APPROVAL_OR_REJECTION",
        },
    }


def _monitor(reference: np.ndarray) -> PredictionMonitor:
    quantiles = {str(q): float(np.quantile(reference, q)) for q in _contract()["score_reference"]["approved_quantiles"]}
    summary = {
        "mean": float(reference.mean()), "quantiles": quantiles,
        "risk_positive_rate": float((reference >= 0.08).mean()), "risk_negative_rate": float((reference < 0.08).mean()),
    }
    bins = {"finite_inner_edges": [0.02, 0.04, 0.06, 0.08, 0.1, 0.2, 0.4, 0.6, 0.8]}
    return PredictionMonitor(_contract(), reference, bins, summary)


def test_threshold_boundary_uses_greater_than_or_equal() -> None:
    classes = apply_threshold(np.array([0.079999999, 0.08, 0.080000001]))
    assert classes.tolist() == ["risk_negative", "risk_positive", "risk_positive"]


def test_reference_against_itself_has_zero_score_psi() -> None:
    reference = np.linspace(0.0, 1.0, 101)
    result = _monitor(reference).evaluate(pd.Series(range(101)), reference, artifact_id="REF", scenario_id="TEST")
    assert np.isclose(result.score_psi["score_psi"], 0.0)
    assert result.score_psi["severity"] == "NORMAL"
    assert result.bin_results["current_count"].sum() == 101
    assert result.bin_results["reference_count"].sum() == 101


def test_score_bin_contributions_reconcile_and_include_edges() -> None:
    reference = np.array([0.0, 0.01, 0.08, 0.5, 1.0])
    current = np.array([0.0, 0.08, 0.08, 1.0, 1.0])
    result = _monitor(reference).evaluate(pd.Series(range(5)), current, artifact_id="EDGE", scenario_id="TEST")
    assert np.isclose(result.bin_results["psi_contribution"].sum(), result.score_psi["score_psi"])
    assert result.threshold_output["risk_positive_count"] == 4
    assert result.threshold_output["risk_negative_count"] == 1


def test_zero_frequency_smoothing_preserves_nonzero_ratio() -> None:
    smoothed = _smooth(np.array([0.0, 0.2, 0.8]), 1e-6)
    assert np.isclose(smoothed.sum(), 1.0)
    assert np.isclose(smoothed[1] / smoothed[2], 0.25)


def test_invalid_probabilities_are_rejected() -> None:
    reference = np.array([0.01, 0.1, 0.5])
    monitor = _monitor(reference)
    for invalid in (np.array([np.nan]), np.array([np.inf]), np.array([-0.1]), np.array([1.1])):
        try:
            monitor.evaluate(pd.Series([1]), invalid, artifact_id="BAD", scenario_id="TEST")
        except RuntimeError:
            pass
        else:
            raise AssertionError("Invalid raw probability was accepted")


def test_raw_probabilities_are_persisted_without_transformation() -> None:
    reference = np.array([0.01, 0.08, 0.5])
    current = np.array([0.0123456789, 0.08, 0.987654321])
    result = _monitor(reference).evaluate(pd.Series([1, 2, 3]), current, artifact_id="RAW", scenario_id="TEST")
    assert np.array_equal(result.predictions["raw_probability"].to_numpy(), current)


def test_phase8_runner_has_no_synthetic_outcome_artifact_dependency() -> None:
    source = inspect.getsource(run_phase8_monitoring)
    assert "SIM-M06-SYNTHETIC-OUTCOMES-01" not in source
    assert "outcomes/SIM-M06" not in source
    root = Path(__file__).resolve().parents[2]
    scope = root / "reports/monitoring/PREDICTION-MONITORING-01/scope_protection_attestation.json"
    if scope.exists():
        payload = json.loads(scope.read_text(encoding="utf-8"))
        assert payload["synthetic_outcomes_loaded"] is False
        assert payload["roc_auc"] is False
        assert payload["calibration"] is False


def test_phase8_final_decision_preserves_scope_gate_when_present() -> None:
    root = Path(__file__).resolve().parents[2]
    decision = root / "reports/monitoring/PREDICTION-MONITORING-01/phase8_completion_decision.json"
    if decision.exists():
        payload = json.loads(decision.read_text(encoding="utf-8"))
        assert payload["technical_qualification"] == "PASS"
        assert payload["review_decision"] == "APPROVED"
        assert payload["phase_8_complete"] is True
        assert payload["threshold_value"] == 0.08
        assert payload["threshold_operator"] == ">="
        assert payload["performance_results_calculated"] is False
        assert payload["threshold_boundary_density_calculated"] is False
        assert payload["phase_9_authorized"] is True
