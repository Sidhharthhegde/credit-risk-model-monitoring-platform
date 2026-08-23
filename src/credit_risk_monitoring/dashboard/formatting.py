"""Presentation-only formatting registry helpers."""

from __future__ import annotations

from typing import Any


STATUS_COLORS = {
    "NORMAL": "#2f855a", "AUTHORIZED": "#2f855a", "OPEN": "#2563eb",
    "WARNING": "#d97706", "ACKNOWLEDGED": "#7c3aed",
    "CRITICAL": "#c2413b", "BLOCKED_HARD_GATE": "#9f1239",
    "BLOCKED_SOURCE_GOVERNANCE": "#9f1239", "RESOLVED": "#475569",
    "NOT_ASSESSABLE": "#64748b", "NOT_ASSESSABLE_FOR_ALERT_AGGREGATION": "#64748b",
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
