from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from credit_risk_monitoring.simulation.generation import apply_scenario, assign_cohorts


def test_assignment_is_balanced_deterministic_and_order_independent() -> None:
    ids = pd.Series(range(100000, 100060), dtype="int64")
    first = assign_cohorts(ids)
    second = assign_cohorts(ids.iloc[::-1])
    assert first.sort_values("SK_ID_CURR").reset_index(drop=True).equals(
        second.sort_values("SK_ID_CURR").reset_index(drop=True)
    )
    assert set(first["simulation_cohort"].value_counts()) == {10}
    assert first["SK_ID_CURR"].is_unique


def test_no_mutation_scenario_is_exact() -> None:
    frame = pd.DataFrame({"SK_ID_CURR": [1, 2], "x": [3.0, 4.0]})
    result, records = apply_scenario(
        frame,
        {"scenario_id": "SIM-M01", "transformations": []},
    )
    assert result.equals(frame)
    assert records == []


def test_transformation_changes_only_declared_feature() -> None:
    frame = pd.DataFrame({"SK_ID_CURR": range(10), "x": [10.0] * 10, "y": [2.0] * 10})
    spec = {
        "scenario_id": "SIM-X",
        "transformations": [
            {
                "transformation_id": "T1",
                "operation": "MULTIPLICATIVE_SHIFT",
                "features": ["x"],
                "factor": 0.5,
                "selection_rate": 0.4,
            }
        ],
    }
    result, records = apply_scenario(frame, spec)
    assert result["y"].equals(frame["y"])
    assert (result["x"] != frame["x"]).sum() == 4
    assert records[0]["changed_features"] == ["x"]


def test_contract_keeps_monitoring_metrics_out_of_phase5() -> None:
    root = Path(__file__).resolve().parents[2]
    contract = json.loads((root / "contracts/simulation_scenario_contract.json").read_text())
    assert contract["cohort_assignment"]["expected_count_per_cohort"] == 8124
    assert contract["cohort_assignment"]["calendar_interpretation"] is False
    assert contract["governance"]["phase_5_monitoring_metrics_permitted"] is False
    assert contract["governance"]["cnd_02_status"] == "OPEN"


def test_phase5_candidate_preserves_review_gate_when_present() -> None:
    root = Path(__file__).resolve().parents[2]
    decision = root / "reports/simulation/SIMULATION-SCENARIO-SET-01/phase5_completion_decision.json"
    if decision.exists():
        payload = json.loads(decision.read_text())
        assert payload["technical_qualification"] == "PASS"
        assert payload["review_decision"] in {"PENDING_USER_PROTOCOL_OWNER_REVIEW", "APPROVED"}
        assert payload["phase_5_complete"] is (payload["review_decision"] == "APPROVED")
        assert payload["monitoring_execution_authorized"] is False
