"""Finalize the owner-approved Phase 15 and Project B release state."""

from pathlib import Path

from credit_risk_monitoring.release.finalization import finalize_phase15


if __name__ == "__main__":
    print(finalize_phase15(Path.cwd()))
