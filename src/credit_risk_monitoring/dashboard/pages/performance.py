from __future__ import annotations

import pandas as pd
import streamlit as st

from credit_risk_monitoring.dashboard.data_service import DashboardDataService
from credit_risk_monitoring.dashboard.formatting import format_metric_value


COMPONENTS = {"PERFORMANCE", "CALIBRATION", "THRESHOLD_PERFORMANCE"}


def render(service: DashboardDataService) -> None:
    st.title("Performance & Calibration")
    scenarios = service.scenarios()
    labels = {row.label: row for row in scenarios}
    selected = labels[st.selectbox("Scenario artifact", list(labels), key="performance_scenario")]
    cols = st.columns(3)
    cols[0].metric("Evidence scope", selected.evidence_scope)
    cols[1].metric("Evidence type", selected.evidence_type)
    cols[2].metric("Overall health", selected.overall_health)

    if selected.evidence_type == "SYNTHETIC_SCENARIO_EVIDENCE":
        st.error(service.policy["disclosures"]["synthetic"])
    if selected.evidence_scope != "FULL_OUTCOME_ELIGIBLE":
        st.warning("OUTCOME STATUS: NOT_ASSESSABLE · OUTCOME_NOT_AVAILABLE. Missing outcome evidence is not zero deterioration and is not NORMAL performance.")

    metrics = [row for row in service.metrics(scenario_id=selected.scenario_id) if row.artifact_id == selected.artifact_id and row.component in COMPONENTS]
    alerts = {(a.metric_id, a.entity_id): a for a in service.alerts(scenario_id=selected.scenario_id) if a.artifact_id == selected.artifact_id}
    table = pd.DataFrame([{
        "Component": row.component, "Metric": row.metric_id, "Value": format_metric_value(row.value),
        "Metric role": row.metric_role, "Evidence status": row.evidence_status,
        "Metric severity": row.metric_severity,
        "Alert severity": alerts[(row.metric_id, row.entity_id)].alert_severity if (row.metric_id, row.entity_id) in alerts else "—",
        "Current alert status": alerts[(row.metric_id, row.entity_id)].current_status if (row.metric_id, row.entity_id) in alerts else "—",
    } for row in metrics])
    st.dataframe(table, hide_index=True, width="stretch")
    st.caption("Direct, supporting, and derived roles are displayed from frozen evidence. The dashboard does not treat them as independent alert drivers.")
    st.info("Reference comparison details are shown only when persisted by the Phase 12 query layer; the dashboard does not reopen Phase 9 files or recompute differences.")
