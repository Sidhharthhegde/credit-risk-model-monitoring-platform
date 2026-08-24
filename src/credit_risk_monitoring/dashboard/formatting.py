"""Presentation-only formatting registry helpers."""

from __future__ import annotations

from typing import Any


STATUS_COLORS = {
    "NORMAL": "#6f9b7a", "AUTHORIZED": "#6f9b7a", "OPEN": "#5f7e98",
    "WARNING": "#c28a43", "ACKNOWLEDGED": "#7772a8",
    "CRITICAL": "#c45d54", "BLOCKED_HARD_GATE": "#773d49",
    "BLOCKED_SOURCE_GOVERNANCE": "#773d49", "RESOLVED": "#596471",
    "NOT_ASSESSABLE": "#596471", "NOT_ASSESSABLE_FOR_ALERT_AGGREGATION": "#596471",
}

MODEL_PASSPORT_METADATA = {
    "model_type": "XGBoost / governed sklearn pipeline",
    "raw_predictors": 176,
    "encoded_predictors": 306,
    "probability": "Raw P(TARGET = 1)",
    "positive_class": 1,
    "production_approved": "NO",
}


def display_label(policy: dict[str, Any], dimension: str, value: str) -> str:
    return str(policy.get("labels", {}).get(dimension, {}).get(value, value.replace("_", " ").title()))


def format_metric_value(value: float | None) -> str:
    if value is None:
        return "N/A"
    magnitude = abs(value)
    if magnitude >= 1000:
        return f"{value:,.0f}"
    if magnitude >= 1:
        return f"{value:,.4f}"
    return f"{value:.6f}"


def status_color(value: str) -> str:
    return STATUS_COLORS.get(value, "#334155")


def technical_label(value: str) -> str:
    """Human-readable label for display; the governed enum remains unchanged."""
    explicit = {
        "LABEL_FREE_ONLY": "Label-free only",
        "FULL_OUTCOME_ELIGIBLE": "Full outcome eligible",
        "NOT_ASSESSABLE": "Not assessable",
        "NOT_ASSESSABLE_FOR_ALERT_AGGREGATION": "Not assessable for alert aggregation",
        "BLOCKED_SOURCE_GOVERNANCE": "Blocked — source governance",
        "BLOCKED_HARD_GATE": "Blocked — hard gate",
        "SYNTHETIC_SCENARIO_EVIDENCE": "Synthetic scenario evidence",
        "MONITORING_EVIDENCE": "Monitoring evidence",
        "CONTROL_QUALIFICATION_EVIDENCE": "Control qualification evidence",
        "INSUFFICIENT_DATA": "Insufficient data",
        "DIRECT_ALERT_DRIVER": "Direct alert driver",
        "SUPPORTING_CORROBORATION": "Supporting corroboration",
        "DERIVED_ONLY": "Derived only",
        "CONTEXT_ONLY": "Context only v1",
    }
    if value in explicit:
        return explicit[value]
    if value == value.upper() and "_" in value:
        return value.replace("_", " ").title()
    return value
