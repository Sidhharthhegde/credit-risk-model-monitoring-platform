"""Frozen six-page dashboard registry."""

from __future__ import annotations

PAGE_REGISTRY = (
    ("OVERVIEW", "Model Monitoring Overview"),
    ("DATA_QUALITY", "Data Quality & Source Governance"),
    ("FEATURE_DRIFT", "Feature Drift"),
    ("PREDICTION", "Prediction Monitoring"),
    ("PERFORMANCE", "Performance & Calibration"),
    ("INVESTIGATION", "Segments, Alerts & Investigation"),
)

# Presentation labels introduced by the Phase 15 control-room redesign. The
# Phase 13 PAGE_REGISTRY above remains unchanged as the frozen page contract.
CONTROL_ROOM_NAVIGATION = (
    ("OVERVIEW", "01", "CONTROL ROOM", "Model Monitoring Overview"),
    ("DATA_QUALITY", "02", "INPUT INTEGRITY", "Data Quality & Source Governance"),
    ("FEATURE_DRIFT", "03", "DRIFT OBSERVATORY", "Feature Drift Monitoring"),
    ("PREDICTION", "04", "MODEL BEHAVIOUR", "Prediction Monitoring"),
    ("PERFORMANCE", "05", "OUTCOME EVIDENCE", "Performance & Calibration Monitoring"),
    ("INVESTIGATION", "06", "INVESTIGATION DESK", "Segments, Alerts & Investigation"),
)
