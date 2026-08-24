"""Shared editorial layout primitives for the Model Risk Control Room."""

from __future__ import annotations

import html
from typing import Iterable

import streamlit as st

from .formatting import technical_label


def page_header(chapter: str, title: str, subtitle: str, *, note: str | None = None) -> None:
    voice = {
        "CONTROL ROOM": "control",
        "INPUT INTEGRITY": "input",
        "DRIFT OBSERVATORY": "drift",
        "MODEL BEHAVIOUR": "model",
        "OUTCOME EVIDENCE": "outcome",
        "INVESTIGATION DESK": "alert",
    }.get(title, "control")
    voice_color = {
        "control": "#BFE6FF",
        "input": "#4BD6A2",
        "drift": "#9A74E8",
        "model": "#5B7CFF",
        "outcome": "#F7B84B",
        "alert": "#FF6B72",
    }[voice]
    st.markdown(
        f'<style>:root{{--chapter-voice:{voice_color};}}</style>'
        f'<div class="control-page-head voice-{voice}"><div class="control-chapter">{html.escape(chapter)}</div>'
        f'<h1>{html.escape(title)}</h1><div class="control-subtitle">{html.escape(subtitle)}</div></div>',
        unsafe_allow_html=True,
    )
    if note:
        st.caption(note)


def section_heading(kicker: str, title: str, description: str | None = None) -> None:
    body = f'<div class="control-section-head"><span>{html.escape(kicker)}</span><h3>{html.escape(title)}</h3>'
    if description:
        body += f'<p>{html.escape(description)}</p>'
    st.markdown(body + "</div>", unsafe_allow_html=True)


def editorial_stat(label: str, value: str | int, *, status: str = "neutral", detail: str | None = None) -> None:
    detail_html = f'<div class="control-stat-detail">{html.escape(detail)}</div>' if detail else ""
    st.markdown(
        f'<div class="control-stat {html.escape(status.lower())}"><div class="control-stat-label">'
        f'{html.escape(label)}</div><div class="control-stat-value">{html.escape(str(value))}</div>{detail_html}</div>',
        unsafe_allow_html=True,
    )


def status_hero(label: str, status: str, *, context: str) -> None:
    st.markdown(
        f'<div class="control-health-hero {status.lower()}"><div><span>{html.escape(label)}</span>'
        f'<strong>{html.escape(technical_label(status))}</strong></div><p>{html.escape(context)}</p></div>',
        unsafe_allow_html=True,
    )


def inspection_rows(rows: Iterable[tuple[str, str, str]]) -> None:
    rendered = []
    for label, value, status in rows:
        rendered.append(
            f'<div class="control-inspection-row"><span>{html.escape(label)}</span>'
            f'<strong class="status-text {html.escape(status.lower())}">{html.escape(technical_label(value))}</strong></div>'
        )
    st.markdown('<div class="control-inspection">' + "".join(rendered) + "</div>", unsafe_allow_html=True)


def disclosure_footer() -> None:
    st.markdown(
        '<div class="control-footer"><span>PRESENTATION INTERFACE · NON-AUTHORITATIVE EVIDENCE LAYER</span>'
        '<span>PORTFOLIO SIMULATION · NOT PRODUCTION DEPLOYMENT</span></div>',
        unsafe_allow_html=True,
    )
