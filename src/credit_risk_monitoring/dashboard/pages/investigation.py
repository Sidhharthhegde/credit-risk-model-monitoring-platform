from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from credit_risk_monitoring.dashboard.casebook_service import CasebookBindingError, load_casebook
from credit_risk_monitoring.dashboard.components.dossier import dossier
from credit_risk_monitoring.dashboard.components.lineage import lineage_panel
from credit_risk_monitoring.dashboard.components.pagination import paginated_table
from credit_risk_monitoring.dashboard.data_service import DashboardDataService
from credit_risk_monitoring.dashboard.formatting import format_metric_value, technical_label
from credit_risk_monitoring.dashboard.layout import editorial_stat, page_header, section_heading
from credit_risk_monitoring.dashboard.query_cache import cached_alerts, cached_metrics


def _casebook_card(case: dict, active: bool) -> None:
    assessment = case["investigation_assessment"]
    disposition = technical_label(assessment["dispositions"][0])
    classes = "casebook-card active" if active else "casebook-card"
    st.markdown(
        f'<div class="{classes}"><span>{html.escape(case["chapter"])}</span>'
        f'<h3>{html.escape(case["short_title"])}</h3>'
        f'<p>{html.escape(" / ".join(technical_label(value) for value in assessment["classification"][:2]))}</p>'
        f'<strong>{html.escape(disposition)}</strong></div>',
        unsafe_allow_html=True,
    )


def _narrative_block(kicker: str, title: str, body: str, *, tone: str = "neutral") -> None:
    st.markdown(
        f'<div class="casebook-narrative {html.escape(tone)}"><span>{html.escape(kicker)}</span>'
        f'<div class="casebook-narrative-title">{html.escape(title)}</div><p>{html.escape(body)}</p></div>',
        unsafe_allow_html=True,
    )


def _evidence_chain(case: dict) -> dict:
    evidence = case["primary_evidence"]
    context = next(
        row for row in case["case_context"]["scenarios"]
        if row["scenario_artifact_id"] == evidence["scenario_artifact_id"]
    )
    nodes = [
        ("HEALTH", context["overall_health"]),
        ("COMPONENT", technical_label(evidence["component"])),
        ("ALERT", technical_label(evidence["alert_severity"])),
        ("METRIC", technical_label(evidence["metric_id"])),
        ("ENTITY", evidence["entity_id"]),
        ("REFERENCE", evidence["reference_id"] or "CONTROL GATE"),
    ]
    rendered = []
    for index, (label, value) in enumerate(nodes):
        rendered.append(
            f'<div class="evidence-chain-node"><span>{html.escape(label)}</span>'
            f'<strong>{html.escape(str(value))}</strong></div>'
        )
        if index < len(nodes) - 1:
            rendered.append('<div class="evidence-chain-link">→</div>')
    st.markdown('<div class="casebook-evidence-chain">' + "".join(rendered) + "</div>", unsafe_allow_html=True)
    return evidence


def _open_case_alert(evidence: dict, scenario_id: str) -> None:
    """Prepare queue state in the widget callback before the next script rerun."""
    st.session_state.update(_queue_navigation_state(evidence, scenario_id))


def _queue_navigation_state(evidence: dict, scenario_id: str) -> dict[str, str]:
    """Bridge a frozen dossier to the dynamic queue without freezing current status."""
    return {
        "investigation_workspace": "Alert Queue",
        "alert_scenario": scenario_id,
        "alert_severity": evidence["alert_severity"],
        "alert_status": "All",
        "alert_component": evidence["component"],
        "alert_dossier": evidence["alert_id"],
    }


def _operational_state_changes(case: dict, current_alerts) -> tuple[dict[str, str], ...]:
    current = {row.alert_id: row.current_status for row in current_alerts}
    changes = []
    for evidence in case["source_evidence"]["linked_alerts"]:
        current_status = current.get(evidence["alert_id"])
        if current_status is not None and current_status != evidence["alert_status_at_extraction"]:
            changes.append({
                "alert_id": evidence["alert_id"],
                "at_extraction": evidence["alert_status_at_extraction"],
                "current": current_status,
            })
    return tuple(changes)


def _casebook_tab(service: DashboardDataService) -> None:
    section_heading(
        "CASEBOOK", "Four consolidated investigations",
        "Derived from governed monitoring evidence. Approved casebook assessments do not rewrite source evidence.",
    )
    try:
        bundle = load_casebook(service.project_root)
    except CasebookBindingError as error:
        st.error(str(error))
        return
    selected_id = st.session_state.setdefault("casebook_selected_case", bundle.registry["default_case_id"])
    columns = st.columns(4)
    for column, case in zip(columns, bundle.cases, strict=True):
        with column:
            _casebook_card(case, case["case_id"] == selected_id)
            if st.button(
                "READ DOSSIER" if case["case_id"] != selected_id else "DOSSIER OPEN",
                key=f"open_{case['case_id']}", use_container_width=True,
                type="primary" if case["case_id"] == selected_id else "secondary",
            ):
                st.session_state["casebook_selected_case"] = case["case_id"]
                st.rerun()

    case = next(row for row in bundle.cases if row["case_id"] == st.session_state["casebook_selected_case"])
    assessment = case["investigation_assessment"]
    contexts = case["case_context"]["scenarios"]
    current_alerts = cached_alerts(service)
    current_status_by_id = {row.alert_id: row.current_status for row in current_alerts}
    state_changes = _operational_state_changes(case, current_alerts)
    st.markdown(
        f'<div class="casebook-case-head"><span>INVESTIGATION {html.escape(case["case_id"])}</span>'
        f'<div class="casebook-case-title">{html.escape(case["title"])}</div><p>Assessment authority · '
        f'{html.escape(technical_label(assessment["authority"]))}</p></div>',
        unsafe_allow_html=True,
    )
    _narrative_block("EXECUTIVE FINDING", "What happened and why it matters", assessment["executive_finding"], tone="finding")
    if state_changes:
        changed_rows = "".join(
            f'<div><code>{html.escape(row["alert_id"])}</code><span>At extraction · '
            f'{html.escape(technical_label(row["at_extraction"]))}</span><strong>Current · '
            f'{html.escape(technical_label(row["current"]))}</strong></div>'
            for row in state_changes
        )
        st.markdown(
            '<div class="casebook-temporal-notice"><span>OPERATIONAL STATE CHANGED SINCE EVIDENCE EXTRACTION</span>'
            f'{changed_rows}<p>The approved investigation assessment remains bound to the extraction-time evidence snapshot.</p></div>',
            unsafe_allow_html=True,
        )

    section_heading("TRACE", "Evidence chain", "Every step resolves to a governed source record; no metric is recalculated here.")
    primary = _evidence_chain(case)
    primary_scenario = next(
        row["scenario_id"] for row in contexts if row["scenario_artifact_id"] == primary["scenario_artifact_id"]
    )
    st.button(
        "OPEN PRIMARY ALERT IN QUEUE", key=f"queue_{case['case_id']}",
        on_click=_open_case_alert, args=(primary, primary_scenario),
    )

    section_heading("SOURCE EVIDENCE", "Governed monitoring record", "Machine-derived values copied exactly from frozen evidence.")
    context_frame = pd.DataFrame([{
        "Artifact": row["scenario_artifact_id"],
        "Authorization": technical_label(row["authorization_state"]),
        "Evidence scope": technical_label(row["evidence_scope"]),
        "Overall health": technical_label(row["overall_health"]),
    } for row in contexts])
    paginated_table(context_frame, key=f"{case['case_id']}_contexts", default_page_size=12)
    linked = case["source_evidence"]["linked_alerts"]
    alert_frame = pd.DataFrame([{
        "Alert ID": row["alert_id"],
        "Component": technical_label(row["component"]),
        "Metric": technical_label(row["metric_id"]),
        "Entity": row["entity_id"],
        "Value": format_metric_value(row["metric_value"]),
        "Metric severity": technical_label(row["metric_severity"]),
        "Alert severity": technical_label(row["alert_severity"]),
        "Status at extraction": technical_label(row["alert_status_at_extraction"]),
        "Current status": technical_label(current_status_by_id.get(row["alert_id"], "NOT_AVAILABLE")),
    } for row in linked])
    paginated_table(alert_frame, key=f"{case['case_id']}_alerts", default_page_size=12)

    section_heading("ASSESSMENT", "Investigation interpretation", "Project-authored interpretation kept semantically separate from source evidence.")
    state_cols = st.columns(4)
    with state_cols[0]:
        editorial_stat("Trigger explanation", technical_label(assessment["alert_trigger_explanation_status"]), detail="Casebook assessment")
    with state_cols[1]:
        editorial_stat("Underlying cause", technical_label(assessment["underlying_cause_status"]), detail="Cause discipline")
    with state_cols[2]:
        editorial_stat("Model defect", technical_label(str(assessment["model_defect_established"]).upper()), detail="Not inferred from alerts")
    with state_cols[3]:
        editorial_stat("Condition", technical_label(assessment["condition_status"]), detail="Remediation not claimed")

    expected = assessment["expected_vs_observed"]
    expected_cols = st.columns(2)
    with expected_cols[0]:
        _narrative_block("CHALLENGE EXPECTATION", "Expected", expected["expected_condition"])
    with expected_cols[1]:
        _narrative_block("MONITORING RESPONSE", "Observed", expected["observed_response"], tone="observed")

    if assessment["control_state_comparison"]:
        st.markdown(
            '<div class="control-section-head"><span>CONTROL STATES</span>'
            '<div class="casebook-section-title">M05-A / M05-B / M05-C</div>'
            '<p>Technical scoreability and governance authority are independent dimensions.</p></div>',
            unsafe_allow_html=True,
        )
        comparison = pd.DataFrame([{
            "Variant": row["variant"],
            "Technical scoring": technical_label(row["technical_scoring"]),
            "Source state": technical_label(row["source_state"]),
            "Authorization": technical_label(row["governance_authorization"]),
            "Downstream monitoring": technical_label(row["downstream_monitoring"]),
            "Health conclusion": technical_label(row["model_health_conclusion"]),
        } for row in assessment["control_state_comparison"]])
        paginated_table(comparison, key="INV-04_comparison", default_page_size=12)

    _narrative_block("CAUSE ASSESSMENT", technical_label(assessment["underlying_cause_status"]), assessment["cause_assessment"])
    st.markdown('<div class="casebook-limitations"><span>EVIDENCE LIMITATIONS</span><ul>' + "".join(
        f'<li>{html.escape(item)}</li>' for item in assessment["evidence_limitations"]
    ) + "</ul></div>", unsafe_allow_html=True)
    _narrative_block("RISK INTERPRETATION", "What the evidence means—and does not mean", assessment["risk_interpretation"], tone="risk")

    disposition_cols = st.columns(2)
    with disposition_cols[0]:
        dossier(
            "Investigation disposition", case["case_id"],
            [("Disposition", " · ".join(assessment["dispositions"])),
             ("Documentation", assessment["documentation_status"]),
             ("Owner review", assessment["owner_review_status"]),
             ("Remediation", assessment["remediation_status"])],
        )
    with disposition_cols[1]:
        dossier(
            "Recommended accountability", assessment["recommended_owner_function"],
            [("Review function", assessment["review_function"]),
             ("Condition", assessment["condition_status"]),
             ("Assessment authority", assessment["authority"])],
        )
    follow_cols = st.columns(2)
    with follow_cols[0]:
        st.markdown("#### Recommended follow-up")
        for item in assessment["recommended_follow_up"]:
            st.markdown(f"- {item}")
    with follow_cols[1]:
        st.markdown("#### Proposed closure evidence")
        for item in assessment["proposed_closure_evidence"]:
            st.markdown(f"- {item}")

    with st.expander("EVIDENCE AS-OF · DUAL PHASE 12 DIGEST BINDING"):
        as_of = case["evidence_as_of"]
        dossier(
            "Evidence extraction boundary", case["case_id"],
            [("Extracted UTC", as_of["evidence_extracted_utc"]),
             ("Immutable evidence digest", as_of["phase12_immutable_evidence_semantic_sha256"]),
             ("Operational database digest", as_of["phase12_operational_database_semantic_sha256_at_extraction"]),
             ("Phase 11 manifest", as_of["phase11_manifest_sha256"]),
             ("Pre-casebook candidate", as_of["phase15_pre_casebook_candidate_manifest_sha256"])],
        )
    st.caption(
        "The monitoring system is authoritative about what it calculated. The casebook assessment is an approved authoritative investigation record. "
        "No alert, severity, health, authorization, evidence type, or lifecycle record is changed by this view."
    )


def _segment_tab(service: DashboardDataService) -> None:
    registry = service.segment_registry()
    section_heading("SEGMENTS", "Frozen segment registry", "Evidence sufficiency is never converted into zero or normal.")
    cols = st.columns(2)
    with cols[0]:
        editorial_stat("Frozen segment families", registry["family_count"], detail="Phase 10 definition registry")
    with cols[1]:
        editorial_stat("Frozen segment levels", registry["level_count"], detail="Context only v1")
    family = st.selectbox("Segment family", [row["name"] for row in registry["families"]])
    selected = next(row for row in registry["families"] if row["name"] == family)
    dossier(
        "Segment record",
        selected["id"],
        [
            ("Family", technical_label(selected["name"])),
            ("Levels", ", ".join(selected["levels"])),
            ("Evidence role", "CONTEXT_ONLY_V1"),
            ("Exploratory demographic", "YES" if selected.get("exploratory_demographic") else "NO"),
        ],
    )
    st.warning(service.policy["disclosures"]["fairness"])
    st.info("DETAILED EVIDENCE NOT AVAILABLE THROUGH GOVERNED QUERY CONTRACT\n\n" + service.policy["governed_unavailable"]["detailed_segment_results"])
    context = cached_metrics(service, component="SEGMENT")
    paginated_table(pd.DataFrame([{
        "Scenario": row.scenario_id,
        "Context metric": technical_label(row.metric_id),
        "Configured levels": format_metric_value(row.value),
        "Metric severity": technical_label(row.metric_severity),
        "Role": technical_label(row.metric_role),
    } for row in context]), key="segment_context", default_page_size=12)
    st.caption("Segment evidence remains CONTEXT_ONLY_V1. No segment alerts or portfolio severity thresholds are introduced.")


def _filter_alerts(service: DashboardDataService, prefix: str):
    scenarios = ["All"] + sorted({row.scenario_id for row in service.scenarios()})
    components = ["All", "DATA_QUALITY", "FEATURE_DRIFT", "PREDICTION", "PERFORMANCE", "CALIBRATION", "THRESHOLD_PERFORMANCE", "GOVERNANCE"]
    scenario_key = f"{prefix}_scenario"
    if scenario_key not in st.session_state:
        st.session_state[scenario_key] = "SIM-M04" if "SIM-M04" in scenarios else "All"
    cols = st.columns(4)
    scenario = cols[0].selectbox(
        "Scenario", scenarios, key=scenario_key,
    )
    severity = cols[1].selectbox("Severity", ["CRITICAL", "WARNING", "All"], key=f"{prefix}_severity")
    status = cols[2].selectbox("Current status", ["OPEN", "ACKNOWLEDGED", "RESOLVED", "All"], key=f"{prefix}_status")
    component = cols[3].selectbox("Component", components, key=f"{prefix}_component")
    return tuple(
        row for row in cached_alerts(service)
        if (scenario == "All" or row.scenario_id == scenario)
        and (severity == "All" or row.alert_severity == severity)
        and (status == "All" or row.current_status == status)
        and (component == "All" or row.component == component)
    )


def _alert_tab(service: DashboardDataService) -> None:
    section_heading("ALERT QUEUE", "Governed alert records", "Metric severity and alert severity remain separate fields.")
    alerts = _filter_alerts(service, "alert")
    evidence_types = ["All"] + sorted({row.evidence_type for row in alerts})
    evidence_type = st.selectbox("Evidence type", evidence_types, key="alert_evidence_type")
    if evidence_type != "All":
        alerts = tuple(row for row in alerts if row.evidence_type == evidence_type)
    paginated_table(pd.DataFrame([{
        "Alert ID": row.alert_id,
        "Scenario": row.scenario_id,
        "Component": technical_label(row.component),
        "Entity": row.entity_id,
        "Metric": technical_label(row.metric_id),
        "Metric severity": technical_label(row.metric_severity),
        "Alert severity": technical_label(row.alert_severity),
        "Current status": technical_label(row.current_status),
    } for row in alerts]), key="alert_queue", default_page_size=12)
    if not alerts:
        st.info("No governed alerts match the selected investigation filters.")
        return
    selected_id = st.selectbox("Open alert dossier", [row.alert_id for row in alerts], key="alert_dossier")
    selected = next(row for row in alerts if row.alert_id == selected_id)
    dossier(
        "Alert record",
        selected.alert_id,
        [
            ("Status", selected.current_status),
            ("Severity", selected.alert_severity),
            ("Scenario", selected.scenario_id),
            ("Component", selected.component),
            ("Metric", selected.metric_id),
            ("Entity", selected.entity_id),
            ("Observed value", format_metric_value(selected.metric_value)),
            ("Metric severity", selected.metric_severity),
            ("Alert severity", selected.alert_severity),
            ("Materiality", selected.materiality_class),
            ("Reason", selected.reason_code),
            ("Evidence type", selected.evidence_type),
            ("Source", selected.source_phase),
        ],
        status=selected.alert_severity,
    )
    lineage_panel(
        control="ALERT-ENGINE-01",
        source_phase=selected.source_phase,
        source_sha256=selected.source_artifact_sha256,
        lineage=selected.lineage,
    )


def _lifecycle_tab(service: DashboardDataService) -> None:
    section_heading("LIFECYCLE", "Alert lifecycle", "OPEN → ACKNOWLEDGED → RESOLVED only.")
    alerts = cached_alerts(service)
    eligible = [row for row in alerts if row.current_status in {"OPEN", "ACKNOWLEDGED"}]
    if not eligible:
        st.info("No alerts are eligible for a forward lifecycle action.")
        return
    scenario = st.selectbox(
        "Scenario scope", sorted({row.scenario_id for row in eligible}),
        index=sorted({row.scenario_id for row in eligible}).index("SIM-M04") if "SIM-M04" in {row.scenario_id for row in eligible} else 0,
        key="lifecycle_scenario",
    )
    eligible = [row for row in eligible if row.scenario_id == scenario]
    selected_id = st.selectbox("Alert", [row.alert_id for row in eligible], key="lifecycle_alert")
    selected = next(row for row in eligible if row.alert_id == selected_id)
    action = "Acknowledge" if selected.current_status == "OPEN" else "Resolve"
    dossier("Lifecycle state", selected.alert_id, [("Current state", selected.current_status), ("Permitted action", action.upper()), ("Actor type", "LOCAL_DEMO_USER")], status=selected.alert_severity)
    if service.lifecycle is None:
        st.info(
            "PUBLIC DEMO · READ-ONLY LIFECYCLE\n\n"
            "This hosted portfolio interface does not persist acknowledgement or resolution events. "
            "Frozen alerts and their current imported state remain available for investigation."
        )
        return
    with st.form("lifecycle_form", clear_on_submit=False):
        st.text_input("Actor label", value="LOCAL_DEMO_USER", disabled=True)
        reason = st.text_area("Investigation / resolution reason")
        confirmed = st.checkbox(f"I confirm the {action.lower()} action")
        submitted = st.form_submit_button(action)
    if submitted:
        try:
            if action == "Acknowledge":
                event_id = service.acknowledge(selected_id, "LOCAL_DEMO_USER", reason, confirmed=confirmed)
            else:
                event_id = service.resolve(selected_id, "LOCAL_DEMO_USER", reason, confirmed=confirmed)
            st.success(f"Lifecycle event appended: {event_id}")
            st.rerun()
        except (ValueError, RuntimeError) as error:
            st.error(str(error))
    st.caption("Lifecycle writes append Phase 12 events through AlertLifecycleService. The frozen alerts table is never updated. Enterprise IAM/RBAC is not represented.")


def _lineage_tab(service: DashboardDataService) -> None:
    section_heading("LINEAGE", "Evidence lineage", "Full hashes stay available without cluttering working tables.")
    alerts = cached_alerts(service)
    scenario = st.selectbox(
        "Scenario scope", sorted({row.scenario_id for row in alerts}),
        index=sorted({row.scenario_id for row in alerts}).index("SIM-M04") if "SIM-M04" in {row.scenario_id for row in alerts} else 0,
        key="lineage_scenario",
    )
    alerts = tuple(row for row in alerts if row.scenario_id == scenario)
    selected_id = st.selectbox("Evidence record", [row.alert_id for row in alerts], key="lineage_alert")
    selected = next(row for row in alerts if row.alert_id == selected_id)
    lineage_panel(
        control="ALERT-ENGINE-01",
        source_phase=selected.source_phase,
        source_sha256=selected.source_artifact_sha256,
        lineage=selected.lineage,
    )


def render(service: DashboardDataService) -> None:
    page_header("06 · INVESTIGATE AND TRACE", "INVESTIGATION DESK", "Casebook, alerts, segments & lineage")
    if "investigation_workspace" not in st.session_state:
        st.session_state["investigation_workspace"] = "Casebook"
    workspace = st.segmented_control(
        "Investigation workspace", ["Casebook", "Alert Queue", "Segments", "Lifecycle", "Lineage"],
        key="investigation_workspace", label_visibility="collapsed",
    )
    if workspace == "Casebook":
        _casebook_tab(service)
    elif workspace == "Alert Queue":
        _alert_tab(service)
    elif workspace == "Segments":
        _segment_tab(service)
    elif workspace == "Lifecycle":
        _lifecycle_tab(service)
    else:
        _lineage_tab(service)
