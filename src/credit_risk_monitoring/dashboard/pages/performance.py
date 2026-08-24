from __future__ import annotations

import pandas as pd
import streamlit as st

from credit_risk_monitoring.dashboard.components.dossier import dossier
from credit_risk_monitoring.dashboard.components.lineage import lineage_panel
from credit_risk_monitoring.dashboard.components.scenario_lab import scenario_lab
from credit_risk_monitoring.dashboard.components.unavailable import unavailable_state
from credit_risk_monitoring.dashboard.data_service import DashboardDataService
from credit_risk_monitoring.dashboard.formatting import format_metric_value, technical_label
from credit_risk_monitoring.dashboard.layout import editorial_stat, page_header, section_heading
from credit_risk_monitoring.dashboard.query_cache import cached_alerts
from credit_risk_monitoring.dashboard.theme import data_table


COMPONENTS = {"PERFORMANCE", "CALIBRATION", "THRESHOLD_PERFORMANCE"}


def render(service: DashboardDataService) -> None:
    page_header(
        "05 · ASSESS OUTCOMES",
        "OUTCOME EVIDENCE",
        "Performance & Calibration Monitoring",
        note="Outcome maturity and evidence sufficiency are independent governance dimensions.",
    )
    selected = scenario_lab(service.scenarios(), key="outcome_scenario")

    if selected.evidence_scope != "FULL_OUTCOME_ELIGIBLE":
        unavailable_state(
            "NOT AVAILABLE",
            "This scenario supports label-free monitoring only. Performance, calibration and realised threshold performance are intentionally not assessable. Missing outcome evidence is not equivalent to normal performance.",
            available=["Data quality", "Feature drift", "Prediction monitoring"],
            unavailable=["ROC-AUC", "Performance KS", "Calibration", "Recall / default capture"],
        )
        st.caption(f"Governed evidence scope: `{selected.evidence_scope}` · Overall health: `{selected.overall_health}`")
        return

    st.markdown(
        '<div class="synthetic-banner">SYNTHETIC OUTCOME LAB · SIM-M06<br>'
        'SYNTHETIC SCENARIO EVIDENCE · NON-EMPIRICAL · NOT EXTERNAL VALIDATION</div>',
        unsafe_allow_html=True,
    )
    metrics = tuple(
        row for row in service.metrics(scenario_id=selected.scenario_id)
        if row.artifact_id == selected.artifact_id and row.component in COMPONENTS
    )
    by_id = {row.metric_id: row for row in metrics}
    section_heading("PRIMARY EVIDENCE", "Synthetic performance instruments", "Reference values are not reconstructed when absent from the Phase 12 query view.")
    cols = st.columns(4)
    for column, metric_id, label in (
        (cols[0], "roc_auc", "ROC-AUC"),
        (cols[1], "performance_ks", "PERFORMANCE KS"),
        (cols[2], "observed_expected_ratio", "O/E RATIO"),
        (cols[3], "recall_default_capture", "RECALL / DEFAULT CAPTURE"),
    ):
        metric = by_id.get(metric_id)
        with column:
            if metric:
                editorial_stat(label, format_metric_value(metric.value), status=metric.metric_severity, detail=technical_label(metric.metric_role))

    alerts = {
        (row.metric_id, row.entity_id): row
        for row in cached_alerts(service)
        if row.scenario_id == selected.scenario_id and row.artifact_id == selected.artifact_id
    }
    section_heading("EVIDENCE DOSSIER", "Metric roles and alert decisions", "Poor supporting or derived metrics do not become independent alert drivers.")
    table = pd.DataFrame([{
        "Component": technical_label(row.component),
        "Metric": technical_label(row.metric_id),
        "Observed value": format_metric_value(row.value),
        "Metric role": technical_label(row.metric_role),
        "Evidence status": technical_label(row.evidence_status),
        "Metric severity": technical_label(row.metric_severity),
        "Alert severity": technical_label(alerts[(row.metric_id, row.entity_id)].alert_severity)
        if (row.metric_id, row.entity_id) in alerts else "—",
    } for row in metrics])
    data_table(table)
    if metrics:
        lineage_panel(
            control="OUTCOME-PERFORMANCE-MONITORING-01",
            source_phase=metrics[0].source_phase,
            source_sha256=metrics[0].source_artifact_sha256,
        )
    st.info("Reference comparisons, synthetic default rate and average PD are not persisted in the governed Phase 12 query view. This interface does not reopen Phase 9 artifacts to recreate them.")
    st.caption(service.policy["disclosures"]["synthetic"])
