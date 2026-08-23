"""Execute the governed Phase 11 alert-engine candidate."""

from __future__ import annotations

import argparse
from pathlib import Path

from credit_risk_monitoring.alert.engine import run_phase11_alert_engine


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--part-a-root", type=Path)
    args = parser.parse_args()
    print(run_phase11_alert_engine(Path.cwd(), args.part_a_root))


if __name__ == "__main__":
    main()
