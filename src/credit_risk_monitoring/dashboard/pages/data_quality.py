from __future__ import annotations

import pandas as pd
import streamlit as st

from credit_risk_monitoring.dashboard.data_service import DashboardDataService
from credit_risk_monitoring.dashboard.formatting import format_metric_value


def render(service: DashboardDataService) -> None:
    st.title("Data Quality & Source Governance")
    st.caption(service.policy["disclosures"]["source_authority"])
    scenarios = service.scenarios()
    labels = {row.label: row for row in scenarios}
    selected_label = st.selectbox("Scenario artifact", list(labels), key="dq_scenario")
    selected = labels[selected_label]

    st.subheader("Authorization and health are separate")
    cols = st.columns(3)
    cols[0].metric("Authorization", selected.authorization)
    cols[1].metric("Evidence scope", selected.evidence_scope)
    cols[2].metric("Overall health", selected.overall_health)
    if selected.authorization != "AUTHORIZED":
        st.warning(f"This artifact is {selected.authorization}. Health remains {selected.overall_health}; a governance block is not a critical model-health result.")

    metrics = service.metrics(component="DATA_QUALITY", scenario_id=selected.scenario_id)
    st.subheader("Governed data-quality findings")
    st.dataframe(pd.DataFrame([{
        "Metric": row.metric_id, "Entity": row.entity_id, "Value": format_metric_value(row.value),
        "Metric severity": row.metric_severity, "Evidence status": row.evidence_status,
        "Reference": row.source_phase, "Source SHA-256": row.source_artifact_sha256,
    } for row in metrics if row.artifact_id == selected.artifact_id]), hide_index=True, width="stretch")

    governance = service.metrics(component="GOVERNANCE", scenario_id=selected.scenario_id)
    if governance:
        st.subheader("Source/governance gate evidence")
        st.dataframe(pd.DataFrame([{
            "Metric": row.metric_id, "Entity": row.entity_id, "Severity": row.metric_severity,
            "Evidence status": row.evidence_status, "Source phase": row.source_phase,
        } for row in governance if row.artifact_id == selected.artifact_id]), hide_index=True, width="stretch")
    st.info("CND-02 remains OPEN. Technical scoring success does not by itself authorize downstream use.")
    st.caption(service.policy["disclosures"]["root_cause"])
