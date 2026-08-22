import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "reports" / "reference" / "REFERENCE-STRATEGY-01"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_reference_roles_and_physical_snapshots_reconcile() -> None:
    strategy = load_json(ROOT / "contracts" / "reference_strategy.json")
    physical = strategy["physical_snapshots"]
    roles = strategy["reference_roles"]
    assert len(roles) == 6
    assert set(roles) == {
        "FEATURE-REF-01",
        "PERF-REF-01",
        "THRESHOLD-SELECTION-REF-01",
        "THRESHOLD-PERF-REF-01",
        "HISTORICAL-CONTEXT-01",
        "APPLICATION-TEST-SIM-01",
    }
    for reference_id, role in roles.items():
        snapshot_id = role["physical_snapshot_id"]
        assert reference_id in physical[snapshot_id]["semantic_roles"]
        assert physical[snapshot_id]["state"] == "SPECIFIED_NOT_MATERIALIZED"
    assert roles["PERF-REF-01"]["physical_snapshot_id"] == roles["THRESHOLD-PERF-REF-01"]["physical_snapshot_id"]


def test_role_matrix_has_one_row_per_governed_reference() -> None:
    strategy = load_json(ROOT / "contracts" / "reference_strategy.json")
    with (PACKAGE / "reference_role_matrix.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["Reference_ID"] for row in rows} == set(strategy["reference_roles"])
    assert len(rows) == len(strategy["reference_roles"])


def test_application_test_adapter_is_label_free_and_not_executed() -> None:
    adapter = load_json(PACKAGE / "application_test_adapter_spec.json")
    tables = {item["table"] for item in adapter["input_sources"]}
    assert tables == {"application_test.csv", "bureau.csv", "previous_application.csv"}
    assert adapter["input_sources"][0]["target_available"] is False
    assert adapter["integration_rule"]["target_dependency_permitted"] is False
    assert adapter["integration_rule"]["training_only_integrator_direct_reuse_permitted"] is False
    cohorts = adapter["simulation_cohort_assignment"]
    assert cohorts["labels"] == [f"SIM-M0{i}" for i in range(1, 7)]
    assert cohorts["calendar_interpretation"] is False
    assert cohorts["status"] == "SPECIFIED_NOT_EXECUTED"
    assert adapter["phase_2_data_access"] == "NO_ROW_DATA_READ_OR_ADAPTED"


def test_methods_are_specified_without_values_or_edges() -> None:
    statistics = load_json(PACKAGE / "future_statistics_specification.json")
    bins = load_json(PACKAGE / "future_psi_bin_specification.json")
    assert statistics["status"] == "METHOD_SPECIFIED_VALUES_NOT_MATERIALIZED"
    assert bins["status"] == "METHOD_SPECIFIED_EDGES_NOT_MATERIALIZED"
    assert statistics["numeric_predictors"]["values_calculated_in_phase_2"] is False
    assert statistics["score_reference"]["values_calculated_in_phase_2"] is False
    assert bins["numeric_feature_bins"]["edges_created_in_phase_2"] is False
    assert bins["score_bins"]["edges_created_in_phase_2"] is False
    assert "observed_bin_edges" not in json.dumps(bins)


def test_phase2_does_not_skip_adapter_qualification_gate() -> None:
    decision = load_json(PACKAGE / "phase2_completion_decision.json")
    assert decision["decision_status"] == "APPROVED"
    assert decision["phase_complete"] is True
    assert decision["feature_adapter_implementation_authorized"] is True
    assert decision["reference_materialization_authorized"] is False
    assert decision["next_phase_authorized"] == "PHASE_3_CONTRACTS_AND_LABEL_FREE_FEATURE_ADAPTER"
    assert decision["materialization_phase"] == "PHASE_4_REFERENCE_MATERIALIZATION_AND_FROZEN_BINS"
    for prohibited_result in (
        "snapshots_materialized",
        "reference_statistics_materialized",
        "psi_bin_edges_created",
        "monitoring_scenarios_created",
        "drift_results_calculated",
        "performance_results_calculated",
        "monitoring_alerts_generated",
    ):
        assert decision[prohibited_result] is False


def test_acceptance_checklist_is_fully_approved() -> None:
    with (PACKAGE / "phase2_acceptance_checklist.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 20
    assert all(row["Status"] == "PASS" for row in rows)
    assert rows[-1]["Evidence"] == "phase2_approval_record.json"
