from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _plan() -> str:
    return (ROOT / "docs/PROJECT_IMPLEMENTATION_PLAN.md").read_text(encoding="utf-8")


def test_authoritative_plan_metadata_is_current() -> None:
    plan = _plan()
    assert "**Plan version:** `1.0.0`" in plan
    assert "**Last updated:** 2026-08-24" in plan
    assert "### Version 1.0.0 change record" in plan


def test_authoritative_overview_ends_at_phase_15() -> None:
    plan = _plan()
    overview = plan.split("# Phase 0", 1)[0]
    phases = [int(value) for value in re.findall(r"^\|\s*(\d+)\s*\|", overview, flags=re.MULTILINE)]
    assert phases == list(range(16))
    assert "Phase 16" not in overview
    assert "Legacy Phase 16" in plan


def test_phase5_scenarios_are_non_calendar_and_not_health_targets() -> None:
    plan = _plan()
    phase5 = plan.split("# Phase 5 - Scenario Framework", 1)[1].split("# Phase 6", 1)[0]
    assert "scenario identifiers, not observation periods or calendar months" in phase5
    assert "no required health state" in phase5
    assert "Stable NORMAL" not in phase5
    assert "required `NORMAL`" not in phase5


def test_pre_remediation_candidate_hash_is_preserved_in_release_builder() -> None:
    source = (ROOT / "src/credit_risk_monitoring/release/qualification.py").read_text(encoding="utf-8")
    assert "2d6c748ab8bfcdb9bb33d96809da2df76651908935b15f79fa76751a1b032781" in source
    assert "PRE_REMEDIATION_PHASE15_TECHNICAL_CANDIDATE" in source
