"""Signature evidence-flow visual for the Model Risk product identity."""

from __future__ import annotations

import html
from typing import Any

import streamlit as st

from ..formatting import technical_label


_NODE_LAYOUT = {
    "DATA_QUALITY": (76, 90, "INPUT", "mint"),
    "FEATURE_DRIFT": (225, 55, "DRIFT", "violet"),
    "PREDICTION": (365, 112, "MODEL", "blue"),
    "PERFORMANCE": (225, 192, "OUTCOME", "amber"),
}

_NODE_PAGES = {
    "DATA_QUALITY": "DATA_QUALITY",
    "FEATURE_DRIFT": "FEATURE_DRIFT",
    "PREDICTION": "PREDICTION",
    "PERFORMANCE": "PERFORMANCE",
}


def evidence_signal_map(component_rows: tuple[dict[str, Any], ...], overall_health: str) -> None:
    """Render the frozen component states as a memorable evidence network."""
    by_component = {row["component"]: row for row in component_rows}
    nodes = []
    for component, (x, y, label, voice) in _NODE_LAYOUT.items():
        row = by_component.get(component)
        state = row["health_state"] if row else "NOT_ASSESSABLE"
        alert_count = int(row["alert_count"]) if row else 0
        hollow = " hollow" if state in {"NOT_ASSESSABLE", "NOT_ASSESSABLE_FOR_ALERT_AGGREGATION"} else ""
        nodes.append(
            f'<a href="?page={_NODE_PAGES[component]}" target="_self" aria-label="Open {html.escape(label.title())}">'
            f'<g class="signal-node {voice} {state.lower()}{hollow}" transform="translate({x} {y})">'
            f'<title>{html.escape(label.title())}: {html.escape(technical_label(state))}; {alert_count} source alerts</title>'
            '<circle class="signal-halo" r="25"/><circle class="signal-core" r="8"/>'
            f'<text class="signal-label" y="-17" text-anchor="middle">{label}</text>'
            f'<text class="signal-state" y="27" text-anchor="middle">{html.escape(technical_label(state).upper())}</text></g></a>'
        )

    health_class = overall_health.lower()
    st.markdown(
        f"""
        <div class="signal-map-shell">
          <div class="signal-map-meta"><span>LIVE EVIDENCE TOPOLOGY</span><b>FROZEN DECISION · READ ONLY</b></div>
          <svg class="signal-map" viewBox="0 0 520 275" role="img" aria-label="Monitoring evidence lifecycle">
            <path class="signal-thread" d="M76 90 C135 62 164 53 225 55 S322 85 365 112 C320 142 276 176 225 192 C174 168 120 125 76 90"/>
            <path class="signal-thread secondary" d="M365 112 C411 129 421 165 433 205"/>
            {''.join(nodes)}
            <a href="?page=INVESTIGATION" target="_self" aria-label="Open Investigation Desk"><g class="signal-node coral {health_class}" transform="translate(433 205)">
              <title>Model health: {html.escape(technical_label(overall_health))}; open the governed investigation queue</title>
              <circle class="signal-halo" r="30"/><circle class="signal-core" r="10"/>
              <text class="signal-label" y="-21" text-anchor="middle">HEALTH</text>
              <text class="signal-state" y="34" text-anchor="middle">{html.escape(technical_label(overall_health).upper())}</text>
            </g></a>
            <text class="signal-footnote" x="18" y="258">CONTROL → OBSERVE → INVESTIGATE → EXPLAIN → TRACE</text>
          </svg>
        </div>
        """,
        unsafe_allow_html=True,
    )


def decision_boundary_strip(*, status: str = "neutral", annotation: str | None = None) -> None:
    detail = html.escape(annotation) if annotation else "Frozen operational policy"
    st.markdown(
        f"""
        <div class="decision-boundary {html.escape(status.lower())}">
          <div class="boundary-head"><span>RAW PROBABILITY SPECTRUM</span><b>{detail}</b></div>
          <div class="boundary-track"><i style="left:8%"></i><div class="boundary-marker" style="left:8%"><em>0.080</em><strong>THRESHOLD-01</strong></div></div>
          <div class="boundary-axis"><span>LOW PD · NEGATIVE DECISION</span><span>HIGH PD · RISK POSITIVE</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
