from __future__ import annotations

from collections import Counter

import pandas as pd
import streamlit as st

from credit_risk_monitoring.dashboard.components.lifecycle import COMPONENT_LABELS, health_explanation
from credit_risk_monitoring.dashboard.components.scenario_lab import SHORT_LABELS, scenario_lab
from credit_risk_monitoring.dashboard.components.signal_map import decision_boundary_strip, evidence_signal_map
from credit_risk_monitoring.dashboard.data_service import DashboardDataService
from credit_risk_monitoring.dashboard.formatting import display_label, technical_label
from credit_risk_monitoring.dashboard.layout import editorial_stat, page_header, section_heading, status_hero
from credit_risk_monitoring.dashboard.query_cache import cached_critical_alerts
from credit_risk_monitoring.dashboard.theme import data_table
from credit_risk_monitoring.dashboard.view_models import ScenarioView


def _open_selected_investigation(artifact_id: str) -> None:
    st.session_state["control_room_scenario_artifact"] = artifact_id
    st.session_state["control_room_active_page"] = "06  INVESTIGATION DESK"
    st.query_params["page"] = "INVESTIGATION"


def _health_context(selected: ScenarioView, component_rows: tuple[dict[str, object], ...]) -> str:
    if selected.authorization == "BLOCKED_SOURCE_GOVERNANCE":
        reason = "Health is not assessable because the source is non-authoritative and no approved fallback exists."
    elif selected.authorization == "BLOCKED_HARD_GATE":
        reason = "Health is not assessable because contract and grain hard gates failed."
    else:
        critical = [row for row in component_rows if row["health_state"] == "CRITICAL"]
        warning = [row for row in component_rows if row["health_state"] == "WARNING"]
        drivers = critical or warning
        if drivers:
            rendered = [
                f"{COMPONENT_LABELS.get(str(row['component']), technical_label(str(row['component'])))} "
                f"has {row['critical_alert_count']} critical and {row['warning_alert_count']} warning alerts"
                for row in drivers
            ]
            reason = f"{technical_label(selected.overall_health)} because " + "; ".join(rendered) + "."
        else:
            reason = f"Frozen overall state: {technical_label(selected.overall_health)}."
    if selected.artifact_id in {"SIM-M01-SCENARIO-01", "SIM-M02-SCENARIO-01"}:
        reason += " Stable control means no injected transformation; it does not mean similarity to the frozen TRAIN reference."
    return f"{selected.label}. {reason} The interface displays the frozen Phase 11 decision; it does not recalculate health."


def _selected_case_path(
    selected: ScenarioView,
    component_rows: tuple[dict[str, object], ...],
) -> str:
    by_component = {str(row["component"]): row for row in component_rows}
    authorization = technical_label(selected.authorization)
    lines = [f"**{selected.label} · governed decision path**", f"01 Authorization — {authorization}"]
    for index, component in enumerate(("DATA_QUALITY", "FEATURE_DRIFT", "PREDICTION", "PERFORMANCE"), start=2):
        row = by_component.get(component)
        state = technical_label(str(row["health_state"])) if row else "Not assessable"
        counts = ""
        if row and int(row["alert_count"]):
            counts = f" · {row['critical_alert_count']} critical / {row['warning_alert_count']} warning"
        lines.append(f"{index:02d} {COMPONENT_LABELS[component].title()} — {state}{counts}")
    lines.append(f"06 Overall model health — {technical_label(selected.overall_health)}")
    return "  \n".join(lines)


def render(service: DashboardDataService) -> None:
    page_header(
        "01 · ENTER CONTROL ROOM",
        "CONTROL ROOM",
        "Model Monitoring Overview",
        note=service.policy["disclosures"]["simulation"],
    )
    snapshot = service.snapshot()
    selected = scenario_lab(snapshot.scenarios, key="overview_scenario_lab")

    component_rows = service.component_health(selected.history_run_id)
    critical_alerts = cached_critical_alerts(service)
    selected_critical = tuple(row for row in critical_alerts if row.artifact_id == selected.artifact_id)
    hero_left, hero_right = st.columns([.82, 1.18], gap="large", vertical_alignment="center")
    with hero_left:
        status_hero(
            "CURRENT MONITORING STATE",
            selected.overall_health,
            context=_health_context(selected, component_rows),
        )
        health_explanation(component_rows, selected.overall_health, selected_critical)
    with hero_right:
        evidence_signal_map(component_rows, selected.overall_health)

    decision_boundary_strip(annotation="probability >= 0.080 · risk positive")
    indicators = st.columns(5)
    with indicators[0]:
        editorial_stat("Portfolio open alerts", snapshot.open_alert_count, status="warning", detail="Across 8 scenario artifacts")
    with indicators[1]:
        editorial_stat("Portfolio critical alerts", snapshot.open_critical_count, status="critical", detail="Individual open alert records")
    with indicators[2]:
        editorial_stat("Blocked scenario runs", snapshot.blocked_run_count, status="blocked", detail="Authorization dimension")
    with indicators[3]:
        editorial_stat("Synthetic outcome", snapshot.synthetic_run_count, status="synthetic", detail="Non-empirical scenario")
    with indicators[4]:
        editorial_stat("Governed records", f"{snapshot.metric_count:,}", detail="Phase 12 query layer")

    open_critical = tuple(row for row in critical_alerts if row.current_status == "OPEN")
    open_critical_by_component = Counter(row.component for row in open_critical)
    open_governance_critical = open_critical_by_component.get("GOVERNANCE", 0)
    with st.expander("HOW TO READ THE PORTFOLIO TOTALS"):
        st.write(
            f"**{snapshot.open_critical_count} critical alerts** counts individual currently open alert records. "
            f"**{snapshot.blocked_run_count} governance blocks** counts scenario runs whose downstream use is not authorized. "
            "These are independent dimensions, not numbers that should be added together."
        )
        if open_governance_critical:
            st.write(
                f"Currently, {open_governance_critical} open governance-gate critical alerts are already included "
                f"within the {snapshot.open_critical_count} critical-alert total."
            )
        data_table(pd.DataFrame([
            {
                "Critical-alert component": COMPONENT_LABELS.get(component, technical_label(component)),
                "Open critical records": count,
            }
            for component, count in sorted(open_critical_by_component.items())
        ]))

    left, right = st.columns([1.08, .92], gap="large")
    with left:
        section_heading("EVIDENCE INDEX", "What the frozen decision can see", "Each component retains its own state; unavailable outcome evidence remains hollow.")
        data_table(pd.DataFrame([{
            "Component": display_label(service.policy, "component", row["component"]),
            "Health": display_label(service.policy, "health", row["health_state"]),
            "Source alerts": row["alert_count"],
            "Critical / warning": f'{row["critical_alert_count"]} / {row["warning_alert_count"]}',
        } for row in component_rows]))
    with right:
        case_alias = SHORT_LABELS.get(selected.artifact_id, selected.scenario_id).split()[0]
        section_heading("CASE PATH", "Selected scenario investigation", "Follow the active case from authorization through component evidence to model health.")
        st.markdown(_selected_case_path(selected, component_rows))
        st.button(
            f"Investigate {case_alias} alerts",
            on_click=_open_selected_investigation,
            args=(selected.artifact_id,),
            type="primary",
            width="stretch",
        )

    section_heading("INVESTIGATION INDEX", "Scenario status matrix", "Governed dimensions remain separate and human-readable.")
    rows = [{
        "Scenario": scenario.label,
        "Authorization": display_label(service.policy, "authorization", scenario.authorization),
        "Evidence scope": display_label(service.policy, "evidence_scope", scenario.evidence_scope),
        "Overall health": display_label(service.policy, "health", scenario.overall_health),
        "Open warnings": scenario.current_warning,
        "Open critical": scenario.current_critical,
        "Synthetic": "Yes" if scenario.synthetic else "No",
    } for scenario in snapshot.scenarios]
    data_table(pd.DataFrame(rows))

    with st.expander("SOURCE COUNTS · CURRENT OPERATIONAL COUNTS · TECHNICAL DETAILS"):
        st.write("Top-line indicators use lifecycle-ledger-derived current counts. Phase 11 source counts remain immutable lineage evidence.")
        data_table(pd.DataFrame([{
            "Scenario": row.label, "Phase 11 source open": row.phase11_source_open,
            "Current open": row.current_open, "Acknowledged": row.current_acknowledged,
            "Resolved": row.current_resolved,
        } for row in snapshot.scenarios]))
    st.info(service.policy["disclosures"]["no_history"])
