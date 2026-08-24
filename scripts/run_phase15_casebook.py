"""Materialize the Phase 15 controlled investigation casebook candidate."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from credit_risk_monitoring.investigation import build_investigation_casebook


if __name__ == "__main__":
    print(build_investigation_casebook(ROOT))
