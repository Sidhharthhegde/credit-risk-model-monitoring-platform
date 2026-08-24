"""Generate the sanitized Phase 15 release-candidate evidence package."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from credit_risk_monitoring.release import run_phase15_qualification


if __name__ == "__main__":
    print(run_phase15_qualification(ROOT))
