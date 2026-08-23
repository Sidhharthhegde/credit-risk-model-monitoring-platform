"""Build and qualify the Phase 12 derived monitoring-history store."""

from pathlib import Path

from credit_risk_monitoring.history.qualification import run_phase12_qualification


if __name__ == "__main__":
    print(run_phase12_qualification(Path.cwd()))
