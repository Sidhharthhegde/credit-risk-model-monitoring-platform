from __future__ import annotations

import pandas as pd
import streamlit as st

from credit_risk_monitoring.dashboard.components.lineage import lineage_panel
from credit_risk_monitoring.dashboard.components.pagination import paginated_table
from credit_risk_monitoring.dashboard.components.scenario_lab import scenario_lab
from credit_risk_monitoring.dashboard.data_service import DashboardDataService
from credit_risk_monitoring.dashboard.formatting import display_label, format_metric_value, technical_label
from credit_risk_monitoring.dashboard.layout import inspection_rows, page_header, section_heading


def render(service: DashboardDataService) -> None:
    page_header(
        "02 · CONTROL INSPECTION",
        "INPUT INTEGRITY",
        "Data Quality & Source Governance",
        note=service.policy["disclosures"]["source_authority"],
    )
    selected = scenario_lab(service.scenarios(), key="input_integrity_scenario")

    section_heading("CONTROL STATE", "Authorization and health remain separate")
    left, right = st.columns([1.05, .95], gap="large")
    with left:
        inspection_rows([
            ("Technical scoreability", "NOT PERSISTED IN PHASE 12 VIEW", "neutral"),
            ("Governance authority", selected.authorization, selected.authorization),
            ("Evidence scope", selected.evidence_scope, "neutral"),
            ("Overall model health", selected.overall_health, selected.overall_health),
            ("CND-02", "OPEN", "warning"),
        ])
    with right:
        if selected.authorization == "BLOCKED_SOURCE_GOVERNANCE":
            st.error(
                "GOVERNANCE AUTHORITY · BLOCKED — SOURCE GOVERNANCE\n\n"
                "Scoring capability and authoritative monitoring use are separate. "
                "The Phase 12 view does not persist the technical-scoring field, so this interface will not reconstruct it."
            )
        elif selected.authorization == "BLOCKED_HARD_GATE":
            st.error("GOVERNANCE AUTHORITY · BLOCKED — HARD GATE\n\nHealth remains Not assessable; it is not presented as Critical.")
        else:
            st.success("GOVERNANCE AUTHORITY · AUTHORIZED")
        with st.expander("GOVERNED ENUMS · TECHNICAL DETAILS"):
            st.code(
                f"authorization={selected.authorization}\n"
                f"evidence_scope={selected.evidence_scope}\n"
                f"overall_health={selected.overall_health}"
            )

    metrics = tuple(
        row for row in service.metrics(component="DATA_QUALITY", scenario_id=selected.scenario_id)
        if row.artifact_id == selected.artifact_id
    )
    section_heading("PHASE 6 EVIDENCE", "Governed data-quality findings", "Hashes move to expandable lineage rather than the working table.")
    paginated_table(pd.DataFrame([{
        "Metric": technical_label(row.metric_id),
        "Entity": row.entity_id,
        "Observed value": format_metric_value(row.value),
        "Severity": technical_label(row.metric_severity),
        "Evidence status": technical_label(row.evidence_status),
        "Reference": row.source_phase.replace("_", " ").title(),
    } for row in metrics]), key="data_quality_evidence", default_page_size=12)
    if metrics:
        lineage_panel(
            control="DATA-QUALITY-CONTROL-01",
            source_phase=metrics[0].source_phase,
            source_sha256=metrics[0].source_artifact_sha256,
        )

    governance = tuple(
        row for row in service.metrics(component="GOVERNANCE", scenario_id=selected.scenario_id)
        if row.artifact_id == selected.artifact_id
    )
    if governance:
        section_heading("AUTHORITY GATE", "Source-governance evidence")
        paginated_table(pd.DataFrame([{
            "Metric": technical_label(row.metric_id), "Entity": row.entity_id,
            "Severity": technical_label(row.metric_severity),
            "Evidence status": technical_label(row.evidence_status),
            "Source phase": row.source_phase,
        } for row in governance]), key="governance_evidence", default_page_size=12)
    st.info("CND-02 remains OPEN. Technical scoring success does not by itself authorize downstream use.")
    st.caption(service.policy["disclosures"]["root_cause"])
