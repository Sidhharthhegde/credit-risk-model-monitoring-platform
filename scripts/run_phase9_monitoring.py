"""Execute Phase 9 synthetic outcome monitoring."""

from __future__ import annotations

import argparse
from pathlib import Path

from credit_risk_monitoring.outcome import run_phase9_monitoring


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--part-a-root", type=Path)
    args = parser.parse_args()
    print(run_phase9_monitoring(args.project_root, args.part_a_root))


if __name__ == "__main__":
    main()
