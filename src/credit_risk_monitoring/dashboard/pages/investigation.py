from __future__ import annotations

import pandas as pd
import streamlit as st

from credit_risk_monitoring.dashboard.data_service import DashboardDataService
from credit_risk_monitoring.dashboard.formatting import format_metric_value


def _segment_tab(service: DashboardDataService) -> None:
    registry = service.segment_registry()
    st.metric("Frozen segment families", registry["family_count"])
    st.metric("Frozen segment levels", registry["level_count"])
    rows = [{"Family ID": family["id"], "Family": family["name"], "Levels": ", ".join(family["levels"]),
             "Exploratory demographic": "Yes" if family.get("exploratory_demographic") else "No"}
            for family in registry["families"]]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.warning(service.policy["disclosures"]["fairness"])
    st.info(service.policy["governed_unavailable"]["detailed_segment_results"])
    context = service.metrics(component="SEGMENT")
    st.dataframe(pd.DataFrame([{"Scenario": row.scenario_id, "Context metric": row.metric_id,
                               "Configured levels": format_metric_value(row.value), "Metric severity": row.metric_severity,
                               "Role": row.metric_role} for row in context]), hide_index=True, width="stretch")
    st.caption("Segment evidence remains CONTEXT_ONLY_V1. No segment alerts or portfolio severity thresholds are introduced.")


def _alert_tab(service: DashboardDataService) -> None:
    scenarios = ["All"] + sorted({row.scenario_id for row in service.scenarios()})
    cols = st.columns(4)
    scenario = cols[0].selectbox("Scenario", scenarios, key="alert_scenario")
    status = cols[1].selectbox("Current status", ["All", "OPEN", "ACKNOWLEDGED", "RESOLVED"], key="alert_status")
    severity = cols[2].selectbox("Alert severity", ["All", "WARNING", "CRITICAL"], key="alert_severity")
    component = cols[3].selectbox("Component", ["All", "DATA_QUALITY", "FEATURE_DRIFT", "PREDICTION", "PERFORMANCE", "CALIBRATION", "THRESHOLD_PERFORMANCE", "GOVERNANCE"], key="alert_component")
    alerts = service.alerts(
        scenario_id=None if scenario == "All" else scenario,
        status=None if status == "All" else status,
        severity=None if severity == "All" else severity,
        component=None if component == "All" else component,
    )
    st.dataframe(pd.DataFrame([{
        "Alert ID": row.alert_id, "Scenario": row.scenario_id, "Component": row.component,
        "Entity": row.entity_id, "Metric": row.metric_id, "Metric severity": row.metric_severity,
        "Alert severity": row.alert_severity, "Current status": row.current_status,
        "Evidence type": row.evidence_type, "Reason": row.reason_code,
    } for row in alerts]), hide_index=True, width="stretch")
    if alerts:
        selected_id = st.selectbox("Alert detail", [row.alert_id for row in alerts], key="alert_detail")
        selected = next(row for row in alerts if row.alert_id == selected_id)
        with st.container(border=True):
            st.subheader(selected.alert_id)
            st.write({
                "scenario": selected.scenario_id, "component": selected.component, "metric": selected.metric_id,
                "entity": selected.entity_id, "metric_value": format_metric_value(selected.metric_value),
                "metric_severity": selected.metric_severity, "alert_severity": selected.alert_severity,
                "metric_role": selected.metric_role, "materiality_class": selected.materiality_class,
                "evidence_status": selected.evidence_status, "evidence_type": selected.evidence_type,
                "source_phase": selected.source_phase, "source_artifact_sha256": selected.source_artifact_sha256,
                "current_status": selected.current_status,
            })
            st.write("Lineage", list(selected.lineage))


def _lifecycle_tab(service: DashboardDataService) -> None:
    alerts = service.alerts()
    eligible = [row for row in alerts if row.current_status in {"OPEN", "ACKNOWLEDGED"}]
    if not eligible:
        st.info("No alerts are eligible for a forward lifecycle action.")
        return
    selected_id = st.selectbox("Alert", [row.alert_id for row in eligible], key="lifecycle_alert")
    selected = next(row for row in eligible if row.alert_id == selected_id)
    action = "Acknowledge" if selected.current_status == "OPEN" else "Resolve"
    st.write(f"Current state: **{selected.current_status}** · permitted action: **{action}**")
    with st.form("lifecycle_form", clear_on_submit=False):
        actor = st.text_input("Actor label", help="Stored as LOCAL_DEMO_USER; this is not enterprise-authenticated identity.")
        reason = st.text_area("Investigation / resolution reason")
        confirmed = st.checkbox(f"I confirm the {action.lower()} action")
        submitted = st.form_submit_button(action)
    if submitted:
        try:
            if action == "Acknowledge":
                event_id = service.acknowledge(selected_id, actor, reason, confirmed=confirmed)
            else:
                event_id = service.resolve(selected_id, actor, reason, confirmed=confirmed)
            st.success(f"Lifecycle event appended: {event_id}")
            st.rerun()
        except (ValueError, RuntimeError) as error:
            st.error(str(error))
    st.caption("Lifecycle writes append Phase 12 events through AlertLifecycleService. The frozen alerts table is never updated.")


def render(service: DashboardDataService) -> None:
    st.title("Segments, Alerts & Investigation")
    segment_tab, alert_tab, lifecycle_tab = st.tabs(["Segment monitoring", "Alerts", "Alert lifecycle"])
    with segment_tab:
        _segment_tab(service)
    with alert_tab:
        _alert_tab(service)
    with lifecycle_tab:
        _lifecycle_tab(service)
