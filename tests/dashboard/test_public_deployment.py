from __future__ import annotations

import json
from pathlib import Path

from credit_risk_monitoring.dashboard.data_service import DashboardDataService
from credit_risk_monitoring.dashboard.state import prepare_database, public_demo_mode
from credit_risk_monitoring.history.digest import semantic_database_manifest
from credit_risk_monitoring.history.store import connect_history


ROOT = Path(__file__).resolve().parents[2]


def test_public_demo_bootstraps_the_frozen_query_database_read_only(tmp_path, monkeypatch) -> None:
    database = tmp_path / "public-demo" / "monitoring_history.db"
    monkeypatch.setenv("CREDIT_RISK_PUBLIC_DEMO", "1")
    monkeypatch.setenv("CREDIT_RISK_HISTORY_DB", str(database))
    assert public_demo_mode() is True
    prepared = prepare_database(ROOT)
    assert prepared == database.resolve()
    assert prepared.is_file()
    connection = connect_history(prepared, read_only=True)
    try:
        semantic = semantic_database_manifest(connection)
    finally:
        connection.close()
    contract = json.loads((ROOT / "contracts/monitoring_dashboard_contract.json").read_text(encoding="utf-8"))
    assert semantic["database_semantic_sha256"] == contract["frozen_phase12_binding"]["initial_database_semantic_sha256"]
    with DashboardDataService(ROOT, prepared, writable=False) as service:
        assert service.lifecycle is None
        assert service.snapshot().alert_count == 329
        assert service.snapshot().metric_count == 2259
    assert prepare_database(ROOT) == prepared


def test_public_entrypoint_and_dependency_surface_are_deployable() -> None:
    entrypoint = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    investigation = (ROOT / "src/credit_risk_monitoring/dashboard/pages/investigation.py").read_text(encoding="utf-8")
    passport = (ROOT / "src/credit_risk_monitoring/dashboard/components/passport.py").read_text(encoding="utf-8")
    assert 'os.environ.setdefault("CREDIT_RISK_PUBLIC_DEMO", "1")' in entrypoint
    assert "streamlit==1.61.1" in requirements
    assert "pyarrow==21.0.0" in requirements
    assert "PUBLIC DEMO · READ-ONLY LIFECYCLE" in investigation
    assert "DOWNLOAD GOVERNED MONITORING REPORT" in passport
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "1.0.0"
    assert (ROOT / "DEPLOYMENT_VERSION").read_text(encoding="utf-8").strip() == "1.0.1"
