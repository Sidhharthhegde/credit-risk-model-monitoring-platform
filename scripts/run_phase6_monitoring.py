"""Execute Phase 6 aggregate data-quality and input controls."""

from __future__ import annotations

import argparse
from pathlib import Path

from credit_risk_monitoring.data_quality import run_phase6_monitoring


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--part-a-root", type=Path)
    args = parser.parse_args()
    print(run_phase6_monitoring(args.project_root, args.part_a_root))


if __name__ == "__main__":
    main()
