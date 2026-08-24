from __future__ import annotations

import streamlit as st


def lineage_panel(*, control: str, source_phase: str, source_sha256: str, lineage: tuple[dict, ...] = ()) -> None:
    with st.expander("EVIDENCE LINEAGE · VIEW TECHNICAL DETAILS"):
        st.markdown(f"**CONTROL**  \n`{control}`")
        st.markdown(f"**SOURCE PHASE**  \n`{source_phase}`")
        st.markdown(f"**SHA-256**  \n`{source_sha256}`")
        if lineage:
            st.markdown("**UPSTREAM LINEAGE**")
            st.json(list(lineage), expanded=False)
