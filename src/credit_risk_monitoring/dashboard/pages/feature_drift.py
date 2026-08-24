from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from credit_risk_monitoring.dashboard.components.dossier import dossier
from credit_risk_monitoring.dashboard.components.lineage import lineage_panel
from credit_risk_monitoring.dashboard.components.pagination import paginated_table
from credit_risk_monitoring.dashboard.components.scenario_lab import scenario_lab
from credit_risk_monitoring.dashboard.data_service import DashboardDataService
from credit_risk_monitoring.dashboard.formatting import format_metric_value, technical_label
from credit_risk_monitoring.dashboard.layout import page_header, section_heading
from credit_risk_monitoring.dashboard.query_cache import cached_alerts
from credit_risk_monitoring.dashboard.theme import SEVERITY_COLORS, style_plotly


def render(service: DashboardDataService) -> None:
    page_header(
        "03 · OBSERVE DISTRIBUTIONS",
        "DRIFT OBSERVATORY",
        "Feature Drift Monitoring",
        note=service.policy["disclosures"]["stable_control"],
    )
    st.caption(service.policy["disclosures"]["root_cause"])
    scenarios = tuple(row for row in service.scenarios() if row.authorization == "AUTHORIZED")
    selected = scenario_lab(scenarios, key="drift_scenario")
    criticality = st.segmented_control(
        "Predictor materiality",
        ["All predictors", "Critical predictors", "Non-critical predictors"],
        default="All predictors",
    )
    metrics = [
        row for row in service.metrics(component="FEATURE_DRIFT", scenario_id=selected.scenario_id)
        if row.artifact_id == selected.artifact_id
    ]
    if criticality == "Critical predictors":
        metrics = [row for row in metrics if row.materiality_class == "TIER_1"]
    elif criticality == "Non-critical predictors":
        metrics = [row for row in metrics if row.materiality_class != "TIER_1"]

    table = pd.DataFrame([{
        "Feature": row.entity_id,
        "PSI": row.value,
        "Metric severity": technical_label(row.metric_severity),
        "Materiality": "Tier 1 / critical predictor" if row.materiality_class == "TIER_1" else technical_label(row.materiality_class),
    } for row in metrics]).sort_values("PSI", ascending=False)

    section_heading("DRIFT RANKING", "Ranked governed PSI signals", "Distribution change relative to FEATURE-REF-01 / TRAIN.")
    view = st.segmented_control(
        "Drift instrument",
        ["Signal field", "Evidence table", "Feature record"],
        default="Signal field",
        key="drift_instrument",
        label_visibility="collapsed",
    )
    if not table.empty and view == "Signal field":
        chart = px.bar(
            table.head(25), x="PSI", y="Feature", color="Metric severity", orientation="h",
            title="RANKED FEATURE PSI · SELECTED EXPERIMENTAL SCENARIO",
            color_discrete_map={technical_label(key): value for key, value in SEVERITY_COLORS.items()},
        )
        chart.update_layout(yaxis={"categoryorder": "total ascending"}, height=650)
        st.plotly_chart(style_plotly(chart), width="stretch", config={"displayModeBar": False, "responsive": True})

    if not table.empty and view in {"Evidence table", "Feature record"}:
        alert_map = {
            (row.metric_id, row.entity_id): row
            for row in cached_alerts(service)
            if row.component == "FEATURE_DRIFT" and row.scenario_id == selected.scenario_id
            and row.artifact_id == selected.artifact_id
        }
        metric_by_entity = {row.entity_id: row for row in metrics}
        table["Alert severity"] = [
            technical_label(alert_map[(metric_by_entity[entity].metric_id, entity)].alert_severity)
            if (metric_by_entity[entity].metric_id, entity) in alert_map else "—" for entity in table["Feature"]
        ]
        table["Alert status"] = [
            technical_label(alert_map[(metric_by_entity[entity].metric_id, entity)].current_status)
            if (metric_by_entity[entity].metric_id, entity) in alert_map else "—" for entity in table["Feature"]
        ]

    if not table.empty and view == "Feature record":
        section_heading("FEATURE", "Inspect a governed signal", "Metric severity and alert severity stay distinct.")
        selected_feature = st.selectbox("Feature dossier", table["Feature"].tolist(), label_visibility="collapsed")
        metric = next(row for row in metrics if row.entity_id == selected_feature)
        alert = alert_map.get((metric.metric_id, metric.entity_id))
        dossier(
            "Feature record",
            metric.entity_id,
            [
                ("PSI", format_metric_value(metric.value)),
                ("Metric severity", metric.metric_severity),
                ("Materiality", "TIER 1 / CRITICAL PREDICTOR" if metric.materiality_class == "TIER_1" else metric.materiality_class),
                ("Alert severity", alert.alert_severity if alert else "NO ALERT"),
                ("Reference", "FEATURE-REF-01 / TRAIN"),
                ("Interpretation", "Observed distribution change relative to the frozen monitoring reference"),
                ("Root cause", "NOT ESTABLISHED"),
            ],
            status=metric.metric_severity,
        )
        lineage_panel(
            control="FEATURE-DRIFT-MONITORING-01",
            source_phase=metric.source_phase,
            source_sha256=metric.source_artifact_sha256,
            lineage=alert.lineage if alert else (),
        )
    if view == "Evidence table":
        paginated_table(table, key="feature_drift_evidence", default_page_size=12)
    st.caption("Metric severity and alert severity are intentionally separate. A critical metric on a non-critical predictor can remain a warning-priority alert.")
