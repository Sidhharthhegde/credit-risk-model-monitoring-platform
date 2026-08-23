from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from credit_risk_monitoring.dashboard.data_service import DashboardDataService


def render(service: DashboardDataService) -> None:
    st.title("Prediction Monitoring")
    st.caption(service.policy["disclosures"]["simulation"])
    metrics = service.metrics(component="PREDICTION")
    scenarios = {row.artifact_id: row.label for row in service.scenarios()}
    alerts = {(a.artifact_id, a.metric_id, a.entity_id): a for a in service.alerts(component="PREDICTION")}
    table = pd.DataFrame([{
        "Scenario": scenarios[row.artifact_id], "Metric": row.metric_id, "Value": row.value,
        "Metric severity": row.metric_severity,
        "Alert status": alerts[(row.artifact_id, row.metric_id, row.entity_id)].current_status if (row.artifact_id, row.metric_id, row.entity_id) in alerts else "—",
    } for row in metrics])
    st.dataframe(table, hide_index=True, width="stretch")
    if not table.empty:
        chart = px.bar(table, x="Scenario", y="Value", color="Metric severity", facet_row="Metric", barmode="group",
                       title="SCENARIO COMPARISON · Governed prediction-monitoring indicators",
                       color_discrete_map={"NORMAL": "#2f855a", "WARNING": "#d97706", "CRITICAL": "#c2413b"})
        chart.update_layout(height=650)
        st.plotly_chart(chart, width="stretch")
    st.info(service.policy["governed_unavailable"]["score_bin_distribution"])
    st.caption("Score PSI and risk-positive-rate change remain separate indicators; no composite prediction-drift score is created.")
