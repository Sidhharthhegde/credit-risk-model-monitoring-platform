"""Launch the local governed Phase 13 Streamlit dashboard."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


if __name__ == "__main__":
    app = Path(__file__).resolve().parents[1] / "src/credit_risk_monitoring/dashboard/app.py"
    raise SystemExit(subprocess.call([sys.executable, "-m", "streamlit", "run", str(app)]))
