"""Dependency-light verification of the tracked public release surface."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "README.md",
    "LICENSE",
    "VERSION",
    "CHANGELOG.md",
    "contracts/final_project_release_contract.json",
    "contracts/model_risk_investigation_contract.json",
    "schemas/scheduled_execution_receipt.schema.json",
    "deployment/scheduling/README.md",
    "deployment/scheduling/cron.example",
    "deployment/scheduling/windows_task_scheduler.xml.example",
    "docs/ARCHITECTURE.md",
    "docs/GOVERNANCE.md",
    "docs/REPRODUCIBILITY.md",
    "docs/SCHEDULED_EXECUTION.md",
    "docs/RELEASE_NOTES_v1.0.0.md",
)


def verify() -> None:
    missing = [path for path in REQUIRED if not (ROOT / path).is_file()]
    if missing:
        raise SystemExit(f"Missing public release files: {', '.join(missing)}")
    contract = json.loads((ROOT / "contracts/final_project_release_contract.json").read_text(encoding="utf-8"))
    assert contract["release"]["version"] == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert contract["execution"]["default_profile"] == "VERIFY_FROZEN"
    assert contract["ci_boundary"]["full_monitoring_execution_claimed"] is False
    assert contract["release"]["tag_creation_requires_owner_approval"] is True
    forbidden = ("C:\\Users\\", "/Users/", "/home/")
    for path in REQUIRED:
        if (ROOT / path).suffix.lower() in {".md", ".json", ".example", ""}:
            text = (ROOT / path).read_text(encoding="utf-8")
            assert not any(token in text for token in forbidden), f"Local path leaked in {path}"


if __name__ == "__main__":
    verify()
    print("Public release surface: PASS")
