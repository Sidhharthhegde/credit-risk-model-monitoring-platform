"""Qualify the Phase 13 dashboard and create its review-candidate package."""

from pathlib import Path

from credit_risk_monitoring.dashboard.qualification import run_phase13_qualification


if __name__ == "__main__":
    print(run_phase13_qualification(Path.cwd()))
