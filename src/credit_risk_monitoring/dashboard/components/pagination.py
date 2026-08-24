"""Presentation-only pagination for governed dashboard tables."""

from __future__ import annotations

import math

import pandas as pd
import streamlit as st

from ..theme import data_table


def _move_page(state_key: str, delta: int, page_count: int) -> None:
    current = int(st.session_state.get(state_key, 1))
    st.session_state[state_key] = min(max(current + delta, 1), page_count)


def paginated_table(
    frame: pd.DataFrame,
    *,
    key: str,
    default_page_size: int = 12,
    page_sizes: tuple[int, ...] = (12, 25, 50),
    height: int | None = None,
) -> None:
    """Render only the visible slice while preserving the governed row order."""
    total = len(frame)
    size_key = f"{key}_page_size"
    page_key = f"{key}_page"
    controls = st.columns([5.8, 1.25, .72, .72], vertical_alignment="center")
    with controls[1]:
        page_size = st.selectbox(
            "Rows per page",
            page_sizes,
            index=page_sizes.index(default_page_size) if default_page_size in page_sizes else 0,
            key=size_key,
            label_visibility="collapsed",
            format_func=lambda value: f"{value} / page",
        )
    page_count = max(1, math.ceil(total / page_size))
    if page_key not in st.session_state:
        st.session_state[page_key] = 1
    if int(st.session_state[page_key]) > page_count:
        st.session_state[page_key] = page_count

    current = int(st.session_state[page_key])
    start = (current - 1) * page_size
    stop = min(start + page_size, total)

    with controls[0]:
        shown = "0" if total == 0 else f"{start + 1}–{stop}"
        st.markdown(
            f'<div class="pagination-readout"><strong>{shown}</strong> of {total:,} governed records'
            f'<span>PAGE {current:02d} / {page_count:02d}</span></div>',
            unsafe_allow_html=True,
        )
    with controls[2]:
        st.button(
            "←", key=f"{key}_previous", disabled=current <= 1, width="stretch",
            on_click=_move_page, args=(page_key, -1, page_count),
        )
    with controls[3]:
        st.button(
            "→", key=f"{key}_next", disabled=current >= page_count, width="stretch",
            on_click=_move_page, args=(page_key, 1, page_count),
        )

    kwargs = {"height": height} if height is not None else {}
    data_table(frame.iloc[start:stop], **kwargs)
