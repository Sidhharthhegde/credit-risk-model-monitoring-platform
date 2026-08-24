"""Local Streamlit dashboard for governed monitoring investigation."""

from __future__ import annotations

import streamlit as st

from credit_risk_monitoring.dashboard.data_service import DashboardBindingError, DashboardDataService
from credit_risk_monitoring.dashboard.components.passport import render_model_passport
from credit_risk_monitoring.dashboard.components.scenario_lab import SHORT_LABELS
from credit_risk_monitoring.dashboard.layout import disclosure_footer
from credit_risk_monitoring.dashboard.navigation import CONTROL_ROOM_NAVIGATION
from credit_risk_monitoring.dashboard.pages import data_quality, feature_drift, investigation, overview, performance, prediction
from credit_risk_monitoring.dashboard.state import database_path, project_root
from credit_risk_monitoring.dashboard.theme import inject_theme


PAGE_RENDERERS = {
    "OVERVIEW": overview.render,
    "DATA_QUALITY": data_quality.render,
    "FEATURE_DRIFT": feature_drift.render,
    "PREDICTION": prediction.render,
    "PERFORMANCE": performance.render,
    "INVESTIGATION": investigation.render,
}


def _navigate(label: str, page_id: str) -> None:
    st.session_state["control_room_active_page"] = label
    st.query_params["page"] = page_id


def main() -> None:
    st.set_page_config(page_title="Credit Risk Monitoring", page_icon="◈", layout="wide")
    inject_theme()
    root = project_root()
    database = database_path(root)
    if not database.is_file():
        st.error("The local Phase 12 monitoring-history database is unavailable. Rebuild MONITORING-HISTORY-01 before opening the dashboard.")
        st.stop()
    try:
        with DashboardDataService(root, database, writable=True) as service:
            snapshot = service.snapshot()
            st.sidebar.markdown(
                "<div class='risk-brand'><i></i><div><span>MODEL / RISK</span><strong>EVIDENCE SYSTEM</strong></div></div>",
                unsafe_allow_html=True,
            )
            st.sidebar.caption("DF-01 / XGBT-01 · FROZEN MODEL")
            navigation = {
                f"{number}  {title}": page_id
                for page_id, number, title, _ in CONTROL_ROOM_NAVIGATION
            }
            compatibility_title = st.sidebar.radio(
                "Navigation state", list(navigation), key="control_room_navigation_state",
                label_visibility="collapsed",
            )
            if st.session_state.get("_control_room_last_compatibility_page") != compatibility_title:
                st.session_state["control_room_active_page"] = compatibility_title
                st.session_state["_control_room_last_compatibility_page"] = compatibility_title
            requested_page = st.query_params.get("page")
            if requested_page in navigation.values():
                requested_label = next(label for label, page_id in navigation.items() if page_id == requested_page)
                if st.session_state.get("_control_room_last_query_page") != requested_page:
                    st.session_state["control_room_active_page"] = requested_label
                    st.session_state["_control_room_last_query_page"] = requested_page
            selected_title = st.session_state.get("control_room_active_page", compatibility_title)
            for label in navigation:
                display_label = f"{label[:2]}  {label[4:].title()}"
                st.sidebar.button(
                    display_label,
                    key=f"nav_{navigation[label].lower()}",
                    on_click=_navigate,
                    args=(label, navigation[label]),
                    type="primary" if label == selected_title else "secondary",
                    width="stretch",
                )
            st.sidebar.divider()
            st.sidebar.markdown(
                f'<div class="risk-sidebar-status"><span class="risk-status-dot"></span>'
                f'{snapshot.open_critical_count} CRITICAL ALERTS · {snapshot.blocked_run_count} GOVERNANCE BLOCKS</div>',
                unsafe_allow_html=True,
            )
            active_artifact = st.session_state.get("control_room_scenario_artifact", "SIM-M04-SCENARIO-01")
            active_case = next((row for row in snapshot.scenarios if row.artifact_id == active_artifact), snapshot.scenarios[0])
            case_alias = SHORT_LABELS.get(active_case.artifact_id, active_case.scenario_id).split()[0]
            st.sidebar.markdown(
                f'<div class="risk-current-case"><span>CURRENT CASE</span><strong>{case_alias}</strong>'
                f'<b class="status-text {active_case.overall_health.lower()}">{active_case.overall_health.replace("_", " ")}</b>'
                f'<small>{active_case.current_critical} critical · {active_case.current_warning} warning alerts</small></div>',
                unsafe_allow_html=True,
            )
            render_model_passport(service.policy["model_card"], root)
            st.sidebar.caption("Presentation interface · non-authoritative evidence")
            st.sidebar.caption("Portfolio simulation · not production deployment")
            PAGE_RENDERERS[navigation[selected_title]](service)
            disclosure_footer()
            st.session_state["_risk_initial_motion_complete"] = True
    except DashboardBindingError as error:
        st.error(f"Dashboard binding failed closed: {error}")
        st.stop()


if __name__ == "__main__":
    main()
