from __future__ import annotations

import html
from collections.abc import Iterable

import streamlit as st

from ..formatting import technical_label


def dossier(title: str, identifier: str, rows: Iterable[tuple[str, str]], *, status: str = "neutral") -> None:
    body = "".join(
        f'<div class="dossier-row"><span>{html.escape(label)}</span><strong>{html.escape(technical_label(value))}</strong></div>'
        for label, value in rows
    )
    st.markdown(
        f'<div class="control-dossier {html.escape(status.lower())}"><div class="dossier-kicker">{html.escape(title)}</div>'
        f'<h3>{html.escape(identifier)}</h3>{body}</div>',
        unsafe_allow_html=True,
    )
