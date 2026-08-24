from __future__ import annotations

import json
from pathlib import Path

from credit_risk_monitoring.dashboard.formatting import MODEL_PASSPORT_METADATA, technical_label
from credit_risk_monitoring.dashboard.navigation import CONTROL_ROOM_NAVIGATION, PAGE_REGISTRY
from credit_risk_monitoring.qualification.binding import sha256_file


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / "src/credit_risk_monitoring/dashboard"


def test_phase13_page_contract_remains_frozen_while_navigation_is_editorial() -> None:
    contract = json.loads((ROOT / "contracts/monitoring_dashboard_contract.json").read_text(encoding="utf-8"))
    assert [(row["page_id"], row["title"]) for row in contract["pages"]] == list(PAGE_REGISTRY)
    assert [row[0] for row in CONTROL_ROOM_NAVIGATION] == [row[0] for row in PAGE_REGISTRY]
    assert [row[2] for row in CONTROL_ROOM_NAVIGATION] == [
        "CONTROL ROOM", "INPUT INTEGRITY", "DRIFT OBSERVATORY",
        "MODEL BEHAVIOUR", "OUTCOME EVIDENCE", "INVESTIGATION DESK",
    ]


def test_frozen_phase13_dependencies_are_unchanged() -> None:
    contract = json.loads((ROOT / "contracts/monitoring_dashboard_contract.json").read_text(encoding="utf-8"))
    binding = contract["frozen_phase12_binding"]
    for path_key, sha_key in (
        ("repository_path", "repository_sha256"),
        ("lifecycle_service_path", "lifecycle_service_sha256"),
    ):
        assert sha256_file(ROOT / binding[path_key]) == binding[sha_key]
    assert sha256_file(ROOT / contract["display_policy"]["path"]) == contract["display_policy"]["sha256"]
    source_binding = json.loads(
        (ROOT / "reports/dashboard/MONITORING-DASHBOARD-01/dashboard_source_binding.json").read_text(encoding="utf-8")
    )
    data_service = next(row for row in source_binding["dashboard_sources"] if row["path"].endswith("data_service.py"))
    assert sha256_file(ROOT / data_service["path"]) == data_service["sha256"]


def test_control_room_components_are_centralized() -> None:
    for path in (
        "layout.py", "theme.py", "components/passport.py", "components/scenario_lab.py",
        "components/lifecycle.py", "components/dossier.py", "components/lineage.py",
        "components/unavailable.py", "components/signal_map.py", "components/pagination.py",
        "query_cache.py",
    ):
        assert (DASHBOARD / path).is_file()


def test_model_passport_matches_frozen_binding_metadata() -> None:
    binding = json.loads((ROOT / "contracts/part_a_binding.json").read_text(encoding="utf-8"))["model"]
    assert MODEL_PASSPORT_METADATA["raw_predictors"] == binding["raw_predictor_count"] == 176
    assert MODEL_PASSPORT_METADATA["encoded_predictors"] == binding["encoded_predictor_count"] == 306
    assert MODEL_PASSPORT_METADATA["positive_class"] == binding["positive_class"] == 1


def test_human_readable_labels_preserve_governed_enum_availability() -> None:
    assert technical_label("LABEL_FREE_ONLY") == "Label-free only"
    assert technical_label("NOT_ASSESSABLE") == "Not assessable"
    assert technical_label("BLOCKED_SOURCE_GOVERNANCE") == "Blocked — source governance"
    assert technical_label("SYNTHETIC_SCENARIO_EVIDENCE") == "Synthetic scenario evidence"


def test_redesign_introduces_no_monitoring_or_raw_evidence_logic() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in DASHBOARD.rglob("*.py")
        if path.name != "qualification.py"
    )
    forbidden = (
        "predict_proba", "roc_auc_score", "calculate_psi", "aggregate_health(",
        "read_parquet", "read_csv", "reports/monitoring/", "sqlite3.connect",
        "if psi >", "threshold = 0.25",
    )
    assert all(token not in source for token in forbidden)
    assert "SYNTHETIC SCENARIO EVIDENCE · NON-EMPIRICAL · NOT EXTERNAL VALIDATION" in source
    assert "Scenario comparison — not chronological history" in source


def test_lifecycle_presentation_uses_only_dashboard_service_transitions() -> None:
    source = (DASHBOARD / "pages/investigation.py").read_text(encoding="utf-8")
    assert "service.acknowledge(" in source
    assert "service.resolve(" in source
    assert "UPDATE alerts" not in source
    assert "LOCAL_DEMO_USER" in source


def test_large_evidence_surfaces_are_paginated_and_investigation_is_lazy() -> None:
    feature = (DASHBOARD / "pages/feature_drift.py").read_text(encoding="utf-8")
    investigation = (DASHBOARD / "pages/investigation.py").read_text(encoding="utf-8")
    prediction = (DASHBOARD / "pages/prediction.py").read_text(encoding="utf-8")
    assert "paginated_table(" in feature
    assert "paginated_table(" in investigation
    assert "paginated_table(" in prediction
    assert "st.tabs(" not in investigation
    assert "st.segmented_control(" in investigation
    assert "cached_alerts(service)" in investigation
    assert '["Casebook", "Alert Queue", "Segments", "Lifecycle", "Lineage"]' in investigation
    assert 'st.session_state["investigation_workspace"] = "Casebook"' in investigation
    assert 'default="Casebook"' not in investigation
    assert "load_casebook(service.project_root)" in investigation
    assert "on_click=_open_case_alert" in investigation
    assert "PRIMARY_EVIDENCE =" not in investigation
    assert 'evidence = case["primary_evidence"]' in investigation
    assert '"alert_status": "All"' in investigation
    assert "OPERATIONAL STATE CHANGED SINCE EVIDENCE EXTRACTION" in investigation


def test_signature_identity_is_model_risk_specific_and_deep_linkable() -> None:
    overview = (DASHBOARD / "pages/overview.py").read_text(encoding="utf-8")
    signal_map = (DASHBOARD / "components/signal_map.py").read_text(encoding="utf-8")
    app = (DASHBOARD / "app.py").read_text(encoding="utf-8")
    assert "evidence_signal_map(" in overview
    assert "THRESHOLD-01" in signal_map and "RAW PROBABILITY SPECTRUM" in signal_map
    assert "st.query_params" in app


def test_finishing_pass_removes_repetitive_ai_typography_patterns() -> None:
    theme = (DASHBOARD / "theme.py").read_text(encoding="utf-8")
    app = (DASHBOARD / "app.py").read_text(encoding="utf-8")
    investigation = (DASHBOARD / "pages/investigation.py").read_text(encoding="utf-8")
    scenarios = (DASHBOARD / "components/scenario_lab.py").read_text(encoding="utf-8")
    assert "Instrument+Serif" in theme and "family=Inter" in theme and "JetBrains+Mono" in theme
    assert "-webkit-background-clip: text" not in theme
    assert "INVESTIGATION CHAPTERS" not in app
    assert "One instrument at a time" not in investigation
    assert all(alias in scenarios for alias in ("M05-A", "M05-B", "M05-C"))


def test_evidence_topology_is_an_investigation_navigation_surface() -> None:
    source = (DASHBOARD / "components/signal_map.py").read_text(encoding="utf-8")
    for page_id in ("DATA_QUALITY", "FEATURE_DRIFT", "PREDICTION", "PERFORMANCE", "INVESTIGATION"):
        assert page_id in source
    assert "source alerts" in source


def test_current_case_is_synchronized_before_the_next_render() -> None:
    source = (DASHBOARD / "components/scenario_lab.py").read_text(encoding="utf-8")
    assert "on_change=_synchronize_current_case" in source
    assert 'st.session_state["control_room_scenario_artifact"] = selected' in source


def test_overview_explanations_are_selected_scenario_specific() -> None:
    overview = (DASHBOARD / "pages/overview.py").read_text(encoding="utf-8")
    lifecycle = (DASHBOARD / "components/lifecycle.py").read_text(encoding="utf-8")
    cache = (DASHBOARD / "query_cache.py").read_text(encoding="utf-8")
    assert "_health_context(selected, component_rows)" in overview
    assert "_selected_case_path(selected, component_rows)" in overview
    assert "HOW TO READ THE PORTFOLIO TOTALS" in overview
    assert "**SIM-M04 · Why is this critical?**" not in overview
    assert "Frozen critical decision drivers" in lifecycle
    assert "cached_critical_alerts" in cache


def test_all_six_control_room_release_views_exist() -> None:
    assets = ROOT / "docs/assets/control_room_after"
    assert sorted(path.name for path in assets.glob("*.jpg")) == [
        "01_control_room.jpg", "02_input_integrity.jpg", "03_drift_observatory.jpg",
        "04_model_behaviour.jpg", "05_outcome_evidence.jpg", "06_investigation_desk.jpg",
    ]
    assert all(path.stat().st_size > 50_000 for path in assets.glob("*.jpg"))
