"""Run the governed Phase 14 monitoring orchestrator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from credit_risk_monitoring.orchestration import MonitoringOrchestrator


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["verify-frozen", "qualification-replay"], default="verify-frozen")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    orchestrator = MonitoringOrchestrator(Path.cwd())
    if args.mode == "verify-frozen":
        result = orchestrator.verify_frozen(generate_report=True)
        print(json.dumps({"mode": result.mode, "status": result.status, "output_root": str(result.output_root)}, indent=2))
    else:
        output = args.output_root or Path.cwd() / "artifacts/qualification_replay/manual_replay"
        result, payload = orchestrator.qualification_replay(output)
        print(json.dumps({"mode": result.mode, "status": result.status, "reconciliation": payload}, indent=2))


if __name__ == "__main__":
    main()
