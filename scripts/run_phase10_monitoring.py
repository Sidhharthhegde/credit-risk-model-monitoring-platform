"""Execute the governed Phase 10 segment-monitoring candidate."""

from __future__ import annotations

import argparse
from pathlib import Path

from credit_risk_monitoring.segment.engine import run_phase10_monitoring


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--part-a-root", type=Path)
    args = parser.parse_args()
    print(run_phase10_monitoring(Path.cwd(), args.part_a_root))


if __name__ == "__main__":
    main()
