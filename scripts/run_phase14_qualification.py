"""Run Phase 14 final-lifecycle technical qualification."""

from pathlib import Path

from credit_risk_monitoring.orchestration.qualification import run_phase14_qualification


if __name__ == "__main__":
    print(run_phase14_qualification(Path.cwd()))
