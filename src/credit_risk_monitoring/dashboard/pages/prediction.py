from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from credit_risk_monitoring.dashboard.components.dossier import dossier
from credit_risk_monitoring.dashboard.components.pagination import paginated_table
from credit_risk_monitoring.dashboard.components.scenario_lab import scenario_lab
from credit_risk_monitoring.dashboard.components.signal_map import decision_boundary_strip
from credit_risk_monitoring.dashboard.data_service import DashboardDataService
from credit_risk_monitoring.dashboard.formatting import format_metric_value, technical_label
from credit_risk_monitoring.dashboard.layout import page_header, section_heading
from credit_risk_monitoring.dashboard.query_cache import cached_alerts
from credit_risk_monitoring.dashboard.theme import SEVERITY_COLORS, style_plotly


def _display_value(metric_id: str, value: float | None) -> str:
    if value is None:
        return "N/A"
    if metric_id == "risk_positive_rate_absolute_change":
        return f"{value * 100:+.2f} pp"
    return f"{value:.4f}"


def render(service: DashboardDataService) -> None:
    page_header(
        "04 · OBSERVE OUTPUTS",
        "MODEL BEHAVIOUR",
        "Prediction Monitoring",
        note="Did the frozen model's output behaviour move?",
    )
    st.caption(service.policy["disclosures"]["simulation"])
    selected = scenario_lab(service.scenarios(), key="behaviour_scenario")
    decision_boundary_strip(status=selected.overall_health, annotation="THRESHOLD-01 · frozen operational boundary")
    metrics = tuple(
        row for row in service.metrics(component="PREDICTION", scenario_id=selected.scenario_id)
        if row.artifact_id == selected.artifact_id
    )
    metric_map = {row.metric_id: row for row in metrics}

    section_heading("OUTPUTS", "Score distribution and threshold composition", "These indicators remain separate; no composite score is created.")
    cols = st.columns(2, gap="large")
    for column, metric_id, title, interpretation in (
        (cols[0], "score_psi", "Score distribution", "Raw probability distribution movement"),
        (cols[1], "risk_positive_rate_absolute_change", "Threshold composition", "Change in risk-positive share at THRESHOLD-01"),
    ):
        with column:
            metric = metric_map.get(metric_id)
            if metric:
                dossier(
                    title,
                    technical_label(metric_id).upper(),
                    [
                        ("Observed value", _display_value(metric_id, metric.value)),
                        ("Metric severity", metric.metric_severity),
                        ("Metric role", metric.metric_role),
                        ("Interpretation", interpretation),
                    ],
                    status=metric.metric_severity,
                )
            else:
                st.info("Indicator not persisted for this governed scenario view.")

    if selected.artifact_id == "SIM-M04-SCENARIO-01":
        st.info("M04 CONTROL STORY · Score PSI is NORMAL while risk-positive-rate change is WARNING. The dashboard does not invent a composite prediction state.")

    section_heading("COMPARISON", "Governed prediction indicators", "Independent simulation scenarios, never a timeline.")
    view = st.segmented_control(
        "Prediction instrument", ["Comparison field", "Evidence ledger"],
        default="Comparison field", key="prediction_instrument", label_visibility="collapsed",
    )
    scenario_rows = service.scenarios()
    all_metrics = tuple(
        metric
        for scenario_id in dict.fromkeys(row.scenario_id for row in scenario_rows)
        for metric in service.metrics(component="PREDICTION", scenario_id=scenario_id)
    )
    scenarios = {row.artifact_id: row.label for row in scenario_rows}
    table = pd.DataFrame([{
        "Scenario": scenarios[row.artifact_id],
        "Metric": technical_label(row.metric_id),
        "Value": row.value,
        "Metric severity": technical_label(row.metric_severity),
    } for row in all_metrics])
    if not table.empty and view == "Comparison field":
        chart = px.bar(
            table, x="Scenario", y="Value", color="Metric severity", facet_row="Metric", barmode="group",
            title="SCENARIO COMPARISON · GOVERNED OUTPUT INDICATORS",
            color_discrete_map={technical_label(key): value for key, value in SEVERITY_COLORS.items()},
        )
        chart.update_layout(height=650)
        st.plotly_chart(style_plotly(chart), width="stretch", config={"displayModeBar": False, "responsive": True})
    if not table.empty and view == "Evidence ledger":
        alerts = {
            (row.artifact_id, row.metric_id, row.entity_id): row
            for row in cached_alerts(service) if row.component == "PREDICTION"
        }
        table["Alert status"] = [
            technical_label(alerts[(metric.artifact_id, metric.metric_id, metric.entity_id)].current_status)
            if (metric.artifact_id, metric.metric_id, metric.entity_id) in alerts else "—"
            for metric in all_metrics
        ]
        paginated_table(table, key="prediction_evidence", default_page_size=12)
    st.info("DETAILED EVIDENCE NOT AVAILABLE THROUGH GOVERNED QUERY CONTRACT\n\n" + service.policy["governed_unavailable"]["score_bin_distribution"])
    st.caption("Score PSI and risk-positive-rate change remain separate indicators; no composite prediction-drift score is created.")
