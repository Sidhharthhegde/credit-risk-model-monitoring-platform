from __future__ import annotations

import pandas as pd
import streamlit as st

from credit_risk_monitoring.dashboard.data_service import DashboardDataService
from credit_risk_monitoring.dashboard.formatting import display_label


def render(service: DashboardDataService) -> None:
    st.title("Model Monitoring Overview")
    st.caption(service.policy["disclosures"]["simulation"])
    model = service.policy["model_card"]
    with st.container(border=True):
        cols = st.columns(4)
        cols[0].metric("Model", model["model_id"])
        cols[1].metric("Version", model["model_version"])
        cols[2].metric("Development freeze", model["development_freeze_id"])
        cols[3].metric(model["threshold_id"], model["threshold_display"])
        st.caption(f"Analytical classes: {model['positive_label']} / {model['negative_label']}. These are not approve/reject decisions.")

    snapshot = service.snapshot()
    cards = st.columns(5)
    cards[0].metric("Current open alerts", snapshot.open_alert_count)
    cards[1].metric("Current open critical", snapshot.open_critical_count)
    cards[2].metric("Blocked runs", snapshot.blocked_run_count)
    cards[3].metric("Synthetic runs", snapshot.synthetic_run_count)
    cards[4].metric("Metric evidence", f"{snapshot.metric_count:,}")

    st.subheader("Scenario status matrix")
    rows = [{
        "Scenario": scenario.label,
        "Authorization": display_label(service.policy, "authorization", scenario.authorization),
        "Evidence scope": display_label(service.policy, "evidence_scope", scenario.evidence_scope),
        "Overall health": display_label(service.policy, "health", scenario.overall_health),
        "Current warnings": scenario.current_warning,
        "Current critical": scenario.current_critical,
        "Current acknowledged": scenario.current_acknowledged,
        "Synthetic": "Yes" if scenario.synthetic else "No",
    } for scenario in snapshot.scenarios]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.subheader("Component health")
    health_rows = []
    for scenario in snapshot.scenarios:
        row = {"Scenario": scenario.label}
        for component in service.component_health(scenario.history_run_id):
            row[component["component"]] = display_label(service.policy, "health", component["health_state"])
        health_rows.append(row)
    st.dataframe(pd.DataFrame(health_rows), hide_index=True, width="stretch")

    with st.expander("Source counts and current operational counts"):
        st.write("Top-line cards use lifecycle-ledger-derived current counts. Phase 11 source counts remain immutable lineage evidence.")
        st.dataframe(pd.DataFrame([{
            "Scenario": s.label, "Phase 11 source open": s.phase11_source_open,
            "Current open": s.current_open, "Acknowledged": s.current_acknowledged, "Resolved": s.current_resolved,
        } for s in snapshot.scenarios]), hide_index=True, width="stretch")

    st.info(service.policy["disclosures"]["no_history"])
