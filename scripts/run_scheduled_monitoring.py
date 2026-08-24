"""Command-line entry point for scheduler-safe frozen monitoring verification."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from credit_risk_monitoring.scheduling import ScheduledExecutionRunner


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument(
        "--profile",
        choices=("VERIFY_FROZEN", "ISOLATED_QUALIFICATION_REPLAY"),
        default="VERIFY_FROZEN",
    )
    parser.add_argument("--recover-stale-lock", action="store_true")
    arguments = parser.parse_args()
    result = ScheduledExecutionRunner(arguments.project_root, runtime_root=arguments.runtime_root).run(
        profile=arguments.profile,
        recover_stale_lock=arguments.recover_stale_lock,
    )
    print(f"execution_id={result.execution_id}")
    print(f"receipt={result.receipt_path}")
    print(f"exit_code={int(result.exit_code)}")
    return int(result.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
