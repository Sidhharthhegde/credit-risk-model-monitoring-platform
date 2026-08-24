from __future__ import annotations

import html
from typing import Any

import streamlit as st

from ..formatting import format_metric_value, technical_label
from ..view_models import AlertView


COMPONENT_LABELS = {
    "DATA_QUALITY": "INPUT INTEGRITY",
    "FEATURE_DRIFT": "FEATURE DRIFT",
    "PREDICTION": "MODEL BEHAVIOUR",
    "PERFORMANCE": "OUTCOME EVIDENCE",
    "CALIBRATION": "CALIBRATION",
    "THRESHOLD_PERFORMANCE": "THRESHOLD POLICY",
    "SEGMENT": "SEGMENT CONTEXT",
    "GOVERNANCE": "GOVERNANCE GATE",
}

METRIC_LABELS = {
    "missing_rate_absolute_change": "Missing-rate absolute change",
    "feature_psi": "Feature PSI",
    "authorization_gate": "Authorization gate",
    "performance_ks": "Performance KS",
    "observed_expected_ratio": "Observed/expected ratio",
    "roc_auc": "ROC AUC",
    "recall_default_capture": "Recall/default capture",
}


def lifecycle_spine(component_rows: tuple[dict[str, Any], ...], overall_health: str) -> None:
    by_component = {row["component"]: row for row in component_rows}
    order = ["DATA_QUALITY", "FEATURE_DRIFT", "PREDICTION", "PERFORMANCE"]
    items = []
    for component in order:
        row = by_component.get(component)
        state = row["health_state"] if row else "NOT_ASSESSABLE"
        items.append(
            f'<div class="lifecycle-node {state.lower()}"><i></i><div><span>{html.escape(COMPONENT_LABELS[component])}</span>'
            f'<strong>{html.escape(technical_label(state))}</strong></div></div>'
        )
    items.extend([
        '<div class="lifecycle-node neutral"><i></i><div><span>ALERT ENGINE</span><strong>Governed aggregation</strong></div></div>',
        f'<div class="lifecycle-node {overall_health.lower()}"><i></i><div><span>MODEL HEALTH</span>'
        f'<strong>{html.escape(technical_label(overall_health))}</strong></div></div>',
    ])
    st.markdown('<div class="lifecycle-spine">' + "".join(items) + "</div>", unsafe_allow_html=True)


def health_explanation(
    component_rows: tuple[dict[str, Any], ...],
    overall_health: str,
    critical_alerts: tuple[AlertView, ...] = (),
) -> None:
    drivers = [
        row for row in component_rows
        if row["health_state"] in {"CRITICAL", "WARNING"} and row["alert_count"]
    ]
    with st.expander("WHY THIS HEALTH STATE?"):
        st.write(
            f"The frozen overall state is **{technical_label(overall_health)}**. "
            "The dashboard does not recalculate this decision."
        )
        if drivers:
            st.markdown("**Governed component findings**")
            for row in drivers:
                st.write(
                    f"- {COMPONENT_LABELS.get(row['component'], technical_label(row['component']))}: "
                    f"{technical_label(row['health_state'])} · {row['alert_count']} source alerts"
                )
        if critical_alerts:
            st.markdown("**Frozen critical decision drivers**")
            for alert in sorted(critical_alerts, key=lambda row: (row.component, row.metric_id, row.entity_id)):
                component = COMPONENT_LABELS.get(alert.component, technical_label(alert.component))
                metric = METRIC_LABELS.get(alert.metric_id, technical_label(alert.metric_id))
                value = format_metric_value(alert.metric_value)
                st.write(
                    f"- {component} · `{alert.entity_id}` — {metric}: `{value}` "
                    f"· {technical_label(alert.current_status)}"
                )
        st.caption("Missing outcome evidence does not override known label-free evidence. Monitoring signals do not establish root cause.")
