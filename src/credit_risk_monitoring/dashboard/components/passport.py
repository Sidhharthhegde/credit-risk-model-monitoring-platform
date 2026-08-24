from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

from ..formatting import MODEL_PASSPORT_METADATA
from ..state import public_demo_mode


def render_model_passport(model: dict[str, str], project_root: Path) -> None:
    with st.sidebar.expander("MODEL PASSPORT"):
        rows = [
            ("MODEL", model["model_id"]),
            ("DEVELOPMENT FREEZE", model["development_freeze_id"]),
            ("MODEL VERSION", model["model_version"]),
            ("MODEL TYPE", MODEL_PASSPORT_METADATA["model_type"]),
            ("RAW PREDICTORS", str(MODEL_PASSPORT_METADATA["raw_predictors"])),
            ("ENCODED PREDICTORS", str(MODEL_PASSPORT_METADATA["encoded_predictors"])),
            ("PROBABILITY", MODEL_PASSPORT_METADATA["probability"]),
            ("POSITIVE CLASS", str(MODEL_PASSPORT_METADATA["positive_class"])),
            ("THRESHOLD", f'{model["threshold_id"]} · {model["threshold_display"]}'),
            ("PRODUCTION APPROVED", MODEL_PASSPORT_METADATA["production_approved"]),
        ]
        body = "".join(
            f'<div class="passport-row"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>'
            for label, value in rows
        )
        st.markdown(f'<div class="model-passport">{body}</div>', unsafe_allow_html=True)
        st.caption("Portfolio simulation · No live lending deployment")
    report = project_root / "reports/monitoring_report/MONITORING-REPORT-01/monitoring_report.html"
    if public_demo_mode():
        st.sidebar.download_button(
            "DOWNLOAD GOVERNED MONITORING REPORT",
            data=report.read_bytes(),
            file_name="model_monitoring_report.html",
            mime="text/html",
            width="stretch",
            on_click="ignore",
        )
    else:
        st.sidebar.link_button("OPEN GOVERNED MONITORING REPORT", report.as_uri(), width="stretch")
