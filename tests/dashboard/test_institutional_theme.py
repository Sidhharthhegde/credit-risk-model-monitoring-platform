from __future__ import annotations

import tomllib
import json
from pathlib import Path

import pandas as pd
import plotly.express as px

from credit_risk_monitoring.dashboard.theme import SEVERITY_COLORS, style_dataframe, style_plotly


ROOT = Path(__file__).resolve().parents[2]


def _relative_luminance(hex_color: str) -> float:
    values = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in values]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(foreground: str, background: str) -> float:
    lighter, darker = sorted((_relative_luminance(foreground), _relative_luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_dark_theme_and_duplicate_streamlit_navigation_are_configured() -> None:
    config = tomllib.loads((ROOT / ".streamlit/config.toml").read_text(encoding="utf-8"))
    assert config["theme"]["base"] == "dark"
    assert config["theme"]["backgroundColor"] == "#0B1016"
    assert config["client"]["showSidebarNavigation"] is False


def test_text_and_severity_contrast_meet_normal_text_target() -> None:
    pairs = [
        ("#F2F0EA", "#0B1016"),
        ("#9AA4B1", "#0B1016"),
        ("#F2F0EA", "#151F2A"),
        ("#9AC3A3", "#1A2820"),
        ("#DDB06D", "#2D2518"),
        ("#DC827A", "#302021"),
    ]
    assert all(_contrast(foreground, background) >= 4.5 for foreground, background in pairs)


def test_severity_palette_is_one_consistent_institutional_system() -> None:
    assert SEVERITY_COLORS == {
        "NORMAL": "#6F9B7A",
        "WARNING": "#C28A43",
        "CRITICAL": "#C45D54",
        "BLOCKED": "#773D49",
        "SYNTHETIC": "#7772A8",
        "NEUTRAL": "#5F7E98",
    }


def test_plotly_theme_uses_dark_surfaces_and_low_opacity_gridlines() -> None:
    figure = style_plotly(px.bar(x=["A", "B"], y=[1, 2]))
    assert figure.layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert figure.layout.plot_bgcolor == "#111923"
    assert figure.layout.xaxis.gridcolor == "rgba(154,164,177,.10)"
    assert figure.layout.yaxis.gridcolor == "rgba(154,164,177,.10)"
    assert figure.layout.transition.duration == 180


def test_table_style_includes_zebra_numeric_and_severity_treatment() -> None:
    frame = pd.DataFrame({"Metric ID": ["m1", "m2"], "Value": [1.0, 2.0], "Severity": ["NORMAL", "CRITICAL"]})
    styler = style_dataframe(frame)
    context = styler._compute().ctx
    flattened = " ".join(f"{name}:{value}" for styles in context.values() for name, value in styles)
    assert "text-align:right" in flattened
    assert "font-family" in flattened
    assert "#1a2820" in flattened
    assert "#302021" in flattened


def test_theme_has_restrained_motion_and_reduced_motion_fallback() -> None:
    source = (ROOT / "src/credit_risk_monitoring/dashboard/theme.py").read_text(encoding="utf-8")
    assert "180ms" in source and "220ms" in source
    assert "prefers-reduced-motion" in source
    assert "particle" not in source.lower()


def test_rerun_entrance_motion_never_animates_opacity() -> None:
    source = (ROOT / "src/credit_risk_monitoring/dashboard/theme.py").read_text(encoding="utf-8")
    card_keyframes = source.split("@keyframes risk-card-in", 1)[1].split("}", 2)[:2]
    chart_keyframes = source.split("@keyframes risk-chart-in", 1)[1].split("}", 2)[:2]
    assert "opacity" not in "".join(card_keyframes)
    assert "opacity" not in "".join(chart_keyframes)


def test_dashboard_launcher_pins_project_root_for_streamlit_config() -> None:
    source = (ROOT / "scripts/run_phase13_dashboard.py").read_text(encoding="utf-8")
    assert 'root = Path(__file__).resolve().parents[1]' in source
    assert "cwd=root" in source


def test_release_motion_contract_is_rerun_safe() -> None:
    contract = json.loads(
        (ROOT / "contracts/final_project_release_contract.json").read_text(encoding="utf-8")
    )["dashboard_release_presentation"]
    assert contract["rerun_entrance_opacity_animation_permitted"] is False
    assert contract["numeric_count_up_scope"] == "FIRST_SESSION_RENDER_ONLY"
    assert contract["streamlit_launcher_must_pin_project_root"] is True
