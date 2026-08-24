from __future__ import annotations

import html

import streamlit as st


def unavailable_state(title: str, explanation: str, *, available: list[str], unavailable: list[str]) -> None:
    left = "".join(f"<li>✓ {html.escape(item)}</li>" for item in available)
    right = "".join(f"<li>— {html.escape(item)}</li>" for item in unavailable)
    st.markdown(
        f'<div class="governed-unavailable"><div class="unavailable-symbol">○</div><span>OUTCOME EVIDENCE</span>'
        f'<h2>{html.escape(title)}</h2><p>{html.escape(explanation)}</p>'
        f'<div class="availability-grid"><div><strong>AVAILABLE</strong><ul>{left}</ul></div>'
        f'<div><strong>NOT AVAILABLE</strong><ul>{right}</ul></div></div></div>',
        unsafe_allow_html=True,
    )
