from __future__ import annotations

import streamlit as st

from ..view_models import ScenarioView


SHORT_LABELS = {
    "SIM-M01-SCENARIO-01": "M01  ○\nStable control · Baseline",
    "SIM-M02-SCENARIO-01": "M02  ◌\nStable control II · Baseline",
    "SIM-M03-SCENARIO-01": "M03  ◒\nMild valid drift · Population",
    "SIM-M04-SCENARIO-01": "M04  ●\nMaterial driver drift · Critical",
    "SIM-M05-VALID-DEGRADED-01": "M05-A  ◐\nSource degradation · Controlled",
    "SIM-M05-SOURCE-LOSS-DIAGNOSTIC-01": "M05-B  ⊘\nSource governance block",
    "SIM-M05-HARD-FAIL-01": "M05-C  ×\nHard contract / grain failure",
    "SIM-M06-SCENARIO-01": "M06  ◉\nSynthetic deterioration · Outcome",
}

SCENARIO_ORDER = tuple(SHORT_LABELS)


def _synchronize_current_case(widget_key: str) -> None:
    """Update the sidebar case before Streamlit begins the next render pass."""
    selected = st.session_state.get(widget_key)
    if selected in SCENARIO_ORDER:
        st.session_state["control_room_scenario_artifact"] = selected


def scenario_lab(
    scenarios: tuple[ScenarioView, ...] | list[ScenarioView], *,
    key: str, default_artifact: str = "SIM-M04-SCENARIO-01",
) -> ScenarioView:
    incoming = {row.artifact_id: row for row in scenarios}
    available = {artifact: incoming[artifact] for artifact in SCENARIO_ORDER if artifact in incoming}
    state_key = "control_room_scenario_artifact"
    if st.session_state.get(state_key) not in available:
        st.session_state[state_key] = default_artifact if default_artifact in available else next(iter(available))
    st.markdown('<div class="scenario-lab-title">Scenario laboratory</div>', unsafe_allow_html=True)
    selected_id = st.radio(
        "Independent experimental scenario",
        list(available),
        index=list(available).index(st.session_state[state_key]),
        format_func=lambda value: SHORT_LABELS.get(value, value),
        horizontal=True,
        key=key,
        on_change=_synchronize_current_case,
        args=(key,),
        label_visibility="collapsed",
    )
    st.session_state[state_key] = selected_id
    st.caption("Scenario comparison — not chronological history. M01–M06 are not calendar periods.")
    return available[selected_id]
