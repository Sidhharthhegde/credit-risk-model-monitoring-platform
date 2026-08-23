from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from credit_risk_monitoring.dashboard.data_service import DashboardDataService


def render(service: DashboardDataService) -> None:
    st.title("Feature Drift")
    st.caption(service.policy["disclosures"]["stable_control"])
    st.caption(service.policy["disclosures"]["root_cause"])
    scenarios = [row for row in service.scenarios() if row.authorization == "AUTHORIZED"]
    labels = {row.label: row for row in scenarios}
    selected = labels[st.selectbox("Authorized scenario", list(labels), key="feature_scenario")]
    criticality = st.radio("Predictor materiality", ["All", "Critical predictors only", "Non-critical predictors"], horizontal=True)
    metrics = [row for row in service.metrics(component="FEATURE_DRIFT", scenario_id=selected.scenario_id) if row.artifact_id == selected.artifact_id]
    if criticality == "Critical predictors only":
        metrics = [row for row in metrics if row.materiality_class == "TIER_1"]
    elif criticality == "Non-critical predictors":
        metrics = [row for row in metrics if row.materiality_class != "TIER_1"]

    alert_map = {(a.metric_id, a.entity_id): a for a in service.alerts(component="FEATURE_DRIFT", scenario_id=selected.scenario_id) if a.artifact_id == selected.artifact_id}
    table = pd.DataFrame([{
        "Feature": row.entity_id, "PSI": row.value, "Metric severity": row.metric_severity,
        "Materiality tier": row.materiality_class,
        "Critical predictor": "Yes" if row.materiality_class == "TIER_1" else "No",
        "Alert severity": alert_map[(row.metric_id, row.entity_id)].alert_severity if (row.metric_id, row.entity_id) in alert_map else "—",
        "Alert status": alert_map[(row.metric_id, row.entity_id)].current_status if (row.metric_id, row.entity_id) in alert_map else "—",
    } for row in metrics]).sort_values("PSI", ascending=False)
    if not table.empty:
        chart = px.bar(table.head(25), x="PSI", y="Feature", color="Metric severity", orientation="h",
                       title="SCENARIO COMPARISON · Ranked governed feature PSI signals",
                       color_discrete_map={"NORMAL": "#2f855a", "WARNING": "#d97706", "CRITICAL": "#c2413b"})
        chart.update_layout(yaxis={"categoryorder": "total ascending"}, height=650)
        st.plotly_chart(chart, width="stretch")
    st.dataframe(table, hide_index=True, width="stretch")
    st.caption("Metric severity and alert severity are intentionally separate. A critical metric on a non-critical predictor can remain a warning-priority alert.")
