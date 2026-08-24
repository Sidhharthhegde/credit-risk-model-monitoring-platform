"""Public, read-only Streamlit Community Cloud entrypoint."""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("CREDIT_RISK_MONITORING_ROOT", str(ROOT))
os.environ.setdefault("CREDIT_RISK_PUBLIC_DEMO", "1")

from credit_risk_monitoring.dashboard.app import main  # noqa: E402


main()
