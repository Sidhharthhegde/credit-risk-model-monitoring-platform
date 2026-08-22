import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "reports" / "adapter" / "FEATURE-ADAPTER-QUALIFICATION-01"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_adapter_contract_has_only_approved_raw_sources() -> None:
    contract = load_json(ROOT / "contracts" / "monitoring_feature_adapter_contract.json")
    assert contract["adapter_id"] == "MONITORING-FEATURE-ADAPTER-01"
    assert {item["source_file"] for item in contract["inputs"].values()} == {
        "application_test.csv",
        "bureau.csv",
        "previous_application.csv",
    }
    assert contract["output"]["predictor_count"] == 176
    assert contract["output"]["target_present"] is False


def test_phase3_manifest_reconciles() -> None:
    manifest_path = PACKAGE / "qualification_manifest.json"
    manifest = load_json(manifest_path)
    assert manifest["artifact_count"] == len(manifest["artifacts"])
    for artifact in manifest["artifacts"]:
        path = PACKAGE / artifact["path"]
        assert path.stat().st_size == artifact["size_bytes"]
        assert sha256(path) == artifact["sha256"]
    assert sha256(manifest_path) == (PACKAGE / "qualification_manifest.sha256").read_text(
        encoding="utf-8"
    ).strip()


def test_dry_run_is_technical_only_and_did_not_persist_rows() -> None:
    dry_run = load_json(PACKAGE / "application_test_dry_run.json")
    assert dry_run["result"] == "PASS"
    assert dry_run["candidate_status"] == "APPLICATION-TEST-BASE-CANDIDATE_NOT_FROZEN"
    assert dry_run["row_level_candidate_persisted"] is False
    assert dry_run["row_level_predictions_persisted"] is False
    assert dry_run["score_summary_persisted"] is False
    assert dry_run["simulation_cohort_assignment_executed"] is False


def test_phase3_approval_authorizes_only_reference_materialization() -> None:
    decision = load_json(PACKAGE / "phase3_completion_decision.json")
    assert decision["decision_status"] == "APPROVED"
    assert decision["technical_qualification_passed"] is True
    assert decision["phase_complete"] is True
    assert decision["reference_materialization_authorized"] is True
    assert decision["monitoring_execution_authorized"] is False
    for field in (
        "snapshots_frozen",
        "reference_statistics_materialized",
        "psi_bin_edges_created",
        "simulation_cohorts_created",
        "drift_results_calculated",
        "performance_results_calculated",
        "monitoring_alerts_generated",
    ):
        assert decision[field] is False


def test_conditional_review_blocker_is_resolved() -> None:
    approval = load_json(PACKAGE / "phase3_approval_record.json")
    assert approval["initial_review_decision"] == "CONDITIONAL_APPROVAL"
    assert approval["initial_blocking_item"] == "PARITY_FIXTURE_BRANCH_COVERAGE_CONFIRMATION"
    assert approval["blocking_item_resolution"] == "PASS"
    assert approval["supplemental_applicant_count"] == 0
    assert approval["reference_materialization_authorized"] is True
    assert approval["monitoring_execution_authorized"] is False


def test_negative_cases_include_numeric_and_binary_contract_failures() -> None:
    evidence = load_json(PACKAGE / "source_control_tests.json")
    cases = {case["case"]: case for case in evidence["cases"]}
    assert cases["non-finite numeric adapter output"]["passed"] is True
    assert cases["invalid binary adapter output"]["passed"] is True


def test_labelled_fixture_covers_material_adapter_branches() -> None:
    coverage = load_json(PACKAGE / "labelled_fixture_coverage.json")
    assert coverage["result"] == "PASS"
    assert all(count > 0 for count in coverage["history_states"].values())
    assert all(coverage["missingness_cases"].values())
    assert all(
        states["zero_present"] and states["one_present"]
        for states in coverage["deterministic_branch_states"].values()
    )
    assert coverage["applicant_ids_persisted"] is False
