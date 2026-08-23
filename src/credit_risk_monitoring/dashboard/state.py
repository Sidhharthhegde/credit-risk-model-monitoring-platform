"""Local dashboard runtime path resolution."""

from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    configured = os.environ.get("CREDIT_RISK_MONITORING_ROOT")
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[3]


def database_path(root: Path) -> Path:
    configured = os.environ.get("CREDIT_RISK_HISTORY_DB")
    if configured:
        return Path(configured).resolve()
    return root / "artifacts/monitoring_history/MONITORING-HISTORY-01/monitoring_history.db"
