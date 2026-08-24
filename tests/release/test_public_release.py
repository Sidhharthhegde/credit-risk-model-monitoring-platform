from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_dependency_light_public_release_check_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/verify_public_release.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout


def test_release_candidate_cannot_self_approve_or_tag() -> None:
    contract = json.loads((ROOT / "contracts/final_project_release_contract.json").read_text(encoding="utf-8"))
    assert contract["approval_gate"]["phase_15_complete_before_owner_approval"] is False
    assert contract["approval_gate"]["project_complete_before_owner_approval"] is False
    assert contract["release"]["candidate_must_not_create_or_push_tag"] is True


def test_ci_is_public_safe_and_does_not_claim_monitoring_execution() -> None:
    contract = json.loads((ROOT / "contracts/final_project_release_contract.json").read_text(encoding="utf-8"))
    workflow = (ROOT / contract["ci_boundary"]["workflow"]).read_text(encoding="utf-8")
    assert "verify_public_release.py" in workflow
    assert "run_scheduled_monitoring.py" not in workflow
    assert contract["ci_boundary"]["full_monitoring_execution_claimed"] is False


def test_scheduler_templates_choose_no_cadence_and_contain_no_local_path() -> None:
    paths = [
        ROOT / "deployment/scheduling/cron.example",
        ROOT / "deployment/scheduling/windows_task_scheduler.xml.example",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "__PROJECT_ROOT__" in text
    assert "C:\\Users\\" not in text
    assert "<Triggers>" in text and "Deployment owner must add" in text


def test_public_docs_preserve_material_limitations() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for statement in ("CND-02", "unlabelled", "synthetic", "not represented as deployed", "CONTROLLED_DEFERRED"):
        assert statement in readme


def test_readme_local_links_resolve() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    targets = re.findall(r"\[[^]]*\]\(([^)]+)\)", readme)
    local = [target.split("#", 1)[0] for target in targets if not target.startswith(("http://", "https://", "#"))]
    assert local
    assert [target for target in local if not (ROOT / target).exists()] == []


def test_release_launchers_and_frozen_report_exist() -> None:
    for path in (
        "scripts/run_scheduled_monitoring.py",
        "scripts/run_phase13_dashboard.py",
        "scripts/run_monitoring_lifecycle.py",
        "reports/monitoring_report/MONITORING-REPORT-01/monitoring_report.html",
        "reports/monitoring_report/MONITORING-REPORT-01/monitoring_report.pdf",
    ):
        assert (ROOT / path).is_file()


def test_runtime_outputs_are_gitignored() -> None:
    candidate = "artifacts/scheduled_execution/SCHEDULED-EXECUTION-01/runs/example/execution_receipt.json"
    result = subprocess.run(
        ["git", "-C", str(ROOT), "check-ignore", candidate],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0


def test_scheduler_example_commands_resolve_to_project_launcher() -> None:
    launcher = ROOT / "scripts/run_scheduled_monitoring.py"
    assert launcher.is_file()
    for path in (ROOT / "deployment/scheduling").glob("*.example"):
        assert "scripts/run_scheduled_monitoring.py" in path.read_text(encoding="utf-8").replace("\\", "/")
