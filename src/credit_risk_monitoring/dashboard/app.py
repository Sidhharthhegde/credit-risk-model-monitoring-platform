"""Local Streamlit dashboard for governed monitoring investigation."""

from __future__ import annotations

import streamlit as st

from credit_risk_monitoring.dashboard.data_service import DashboardBindingError, DashboardDataService
from credit_risk_monitoring.dashboard.navigation import PAGE_REGISTRY
from credit_risk_monitoring.dashboard.pages import data_quality, feature_drift, investigation, overview, performance, prediction
from credit_risk_monitoring.dashboard.state import database_path, project_root


PAGE_RENDERERS = {
    "OVERVIEW": overview.render,
    "DATA_QUALITY": data_quality.render,
    "FEATURE_DRIFT": feature_drift.render,
    "PREDICTION": prediction.render,
    "PERFORMANCE": performance.render,
    "INVESTIGATION": investigation.render,
}


def _style() -> None:
    st.markdown("""
    <style>
      .stApp { background: #f6f7f9; color: #172033; }
      [data-testid="stSidebar"] { background: #172033; }
      [data-testid="stSidebar"] * { color: #f8fafc; }
      div[data-testid="stMetric"] { background: white; border: 1px solid #dce2ea; border-radius: 12px; padding: 14px; }
      h1, h2, h3 { letter-spacing: -0.02em; }
      .stAlert { border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(page_title="Credit Risk Monitoring", page_icon="◈", layout="wide")
    _style()
    root = project_root()
    database = database_path(root)
    st.sidebar.title("Model Risk Monitoring")
    st.sidebar.caption("DF-01 / XGBT-01")
    page_titles = {title: page_id for page_id, title in PAGE_REGISTRY}
    selected_title = st.sidebar.radio("Investigation area", list(page_titles), label_visibility="collapsed")
    st.sidebar.divider()
    st.sidebar.caption("Presentation interface · non-authoritative evidence")
    if not database.is_file():
        st.error("The local Phase 12 monitoring-history database is unavailable. Rebuild MONITORING-HISTORY-01 before opening the dashboard.")
        st.stop()
    try:
        with DashboardDataService(root, database, writable=True) as service:
            PAGE_RENDERERS[page_titles[selected_title]](service)
    except DashboardBindingError as error:
        st.error(f"Dashboard binding failed closed: {error}")
        st.stop()


if __name__ == "__main__":
    main()
