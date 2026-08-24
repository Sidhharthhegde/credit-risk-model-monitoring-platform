"""Local dashboard runtime path resolution."""

from __future__ import annotations

import os
import json
import tempfile
import threading
import uuid
from pathlib import Path

from credit_risk_monitoring.history.ingest import HistoryIngestor


def project_root() -> Path:
    configured = os.environ.get("CREDIT_RISK_MONITORING_ROOT")
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[3]


def database_path(root: Path) -> Path:
    configured = os.environ.get("CREDIT_RISK_HISTORY_DB")
    if configured:
        return Path(configured).resolve()
    if public_demo_mode():
        return Path(tempfile.gettempdir()) / "credit-risk-model-monitoring" / "monitoring_history.db"
    return root / "artifacts/monitoring_history/MONITORING-HISTORY-01/monitoring_history.db"


def public_demo_mode() -> bool:
    return os.environ.get("CREDIT_RISK_PUBLIC_DEMO", "").strip().lower() in {"1", "true", "yes"}


_PUBLIC_DATABASE_BUILD_LOCK = threading.Lock()


def prepare_database(root: Path) -> Path:
    """Return the local database or build a governed ephemeral public-demo copy."""
    database = database_path(root)
    if database.is_file() or not public_demo_mode():
        return database
    with _PUBLIC_DATABASE_BUILD_LOCK:
        if database.is_file():
            return database
        database.parent.mkdir(parents=True, exist_ok=True)
        candidate = database.with_name(f".{database.name}.{uuid.uuid4().hex}.tmp")
        try:
            result = HistoryIngestor(root, candidate).ingest()
            dashboard_contract = json.loads(
                (root / "contracts/monitoring_dashboard_contract.json").read_text(encoding="utf-8")
            )
            expected = dashboard_contract["frozen_phase12_binding"]["initial_database_semantic_sha256"]
            if result.semantic_manifest["database_semantic_sha256"] != expected:
                raise RuntimeError("Public-demo database does not match the frozen Phase 12 semantic digest")
            os.replace(candidate, database)
        finally:
            if candidate.is_file():
                candidate.unlink()
    return database
