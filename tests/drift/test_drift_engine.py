from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from credit_risk_monitoring.drift.engine import FeatureDriftMonitor, _smooth


def _monitor(reference: pd.DataFrame) -> FeatureDriftMonitor:
    contract = {"psi_policy": {"epsilon": 1e-6, "warning": 0.10, "critical": 0.25}}
    definitions = [
        {
            "feature": "num", "feature_type": "NUMERIC", "finite_inner_edges": [0.5],
            "missing_bucket": "__MISSING__", "reference_id": "FEATURE-REF-01",
        },
        {
            "feature": "cat", "feature_type": "CATEGORICAL", "reference_levels": ["A", "B"],
            "missing_bucket": "__MISSING__", "unseen_bucket": "__UNSEEN__", "reference_id": "FEATURE-REF-01",
        },
    ]
    materiality = {
        feature: {"materiality_tier": "TIER_1", "part_a_shap_rank": rank, "part_a_shap_share": 0.5, "feature_family": "TEST"}
        for rank, feature in enumerate(["num", "cat"], 1)
    }
    return FeatureDriftMonitor(contract, definitions, reference, materiality)


def test_identical_population_has_zero_psi() -> None:
    reference = pd.DataFrame({"num": [0.0, 0.0, 1.0, 1.0], "cat": ["A", "A", "B", "B"]})
    result = _monitor(reference).evaluate(reference.copy(), artifact_id="IDENTICAL", scenario_id="TEST")
    assert np.allclose(result.feature_results["psi"], 0.0)
    assert set(result.feature_results["severity"]) == {"NORMAL"}
    assert result.summary["feature_result_count"] == 2


def test_psi_matches_hand_calculation() -> None:
    reference = pd.DataFrame({"num": [0.0] * 50 + [1.0] * 50, "cat": ["A"] * 50 + ["B"] * 50})
    current = pd.DataFrame({"num": [0.0] * 80 + [1.0] * 20, "cat": ["A"] * 80 + ["B"] * 20})
    result = _monitor(reference).evaluate(current, artifact_id="SHIFT", scenario_id="TEST")
    expected = (0.8 - 0.5) * np.log(0.8 / 0.5) + (0.2 - 0.5) * np.log(0.2 / 0.5)
    assert np.isclose(result.feature_results.loc[result.feature_results["feature"] == "num", "psi"].iloc[0], expected)


def test_missing_and_unseen_buckets_reconcile() -> None:
    reference = pd.DataFrame({"num": [0.0, 1.0, np.nan, 1.0], "cat": ["A", "B", None, "A"]})
    current = pd.DataFrame({"num": [0.0, np.nan, 1.0, np.nan], "cat": ["A", "NEW", None, "NEW"]})
    result = _monitor(reference).evaluate(current, artifact_id="BUCKETS", scenario_id="TEST")
    for _, group in result.bin_results.groupby("feature"):
        assert group["reference_count"].sum() == len(reference)
        assert group["current_count"].sum() == len(current)
        assert np.isclose(group["reference_proportion_smoothed"].sum(), 1.0)
        assert np.isclose(group["current_proportion_smoothed"].sum(), 1.0)
    cat = result.feature_results.loc[result.feature_results["feature"] == "cat"].iloc[0]
    assert cat["current_unseen_rate"] == 0.5
    assert cat["current_missing_rate"] == 0.25


def test_zero_frequency_smoothing_replaces_only_zero_then_renormalizes() -> None:
    smoothed = _smooth(np.array([0.0, 0.25, 0.75]), 1e-6)
    assert np.isclose(smoothed.sum(), 1.0)
    assert smoothed[0] > 0
    assert np.isclose(smoothed[1] / smoothed[2], 1 / 3)


def test_p_values_are_supporting_and_do_not_drive_severity() -> None:
    reference = pd.DataFrame({"num": np.linspace(0, 1, 10000), "cat": ["A", "B"] * 5000})
    current = reference.copy()
    current["num"] += 1e-5
    result = _monitor(reference).evaluate(current, artifact_id="LARGE", scenario_id="TEST")
    numeric = result.numeric_diagnostics.iloc[0]
    feature = result.feature_results.loc[result.feature_results["feature"] == "num"].iloc[0]
    assert numeric["control_role"] == "SUPPORTING"
    assert not numeric["p_value_drove_severity"]
    assert not feature["p_value_drove_severity"]
    assert not feature["alert_generated"]


def test_phase7_final_decision_preserves_scope_gates_when_present() -> None:
    root = Path(__file__).resolve().parents[2]
    decision = root / "reports/monitoring/FEATURE-DRIFT-MONITORING-01/phase7_completion_decision.json"
    if decision.exists():
        payload = json.loads(decision.read_text(encoding="utf-8"))
        assert payload["technical_qualification"] == "PASS"
        assert payload["review_decision"] == "APPROVED"
        assert payload["phase_7_complete"] is True
        assert payload["feature_psi_result_count"] == 1056
        assert payload["monitoring_alerts_generated"] is False
        assert payload["phase_8_authorized"] is True
