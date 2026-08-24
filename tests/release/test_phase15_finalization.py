from __future__ import annotations

import json
from pathlib import Path

import pytest

from credit_risk_monitoring.qualification.binding import sha256_file
from credit_risk_monitoring.release.finalization import (
    APPROVED_ALERT_EVENT_LEDGER_SHA256,
    APPROVED_CASEBOOK_SHA256,
    PRE_FINALIZATION_CANDIDATE_SHA256,
    RELEASE_TAG,
    finalize_phase15,
)
from credit_risk_monitoring.release.qualification import run_phase15_qualification


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports/release/PROJECT-RELEASE-01"


def _json(name: str) -> dict:
    return json.loads((REPORT / name).read_text(encoding="utf-8"))


def test_phase15_and_project_b_are_owner_approved_and_complete() -> None:
    decision = _json("phase15_completion_decision.json")
    project = _json("project_completion_decision.json")
    assert decision["decision"] == "APPROVED_FROZEN"
    assert decision["owner_approval_recorded"] is True
    assert decision["phase_15_complete"] is True
    assert decision["project_b_complete"] is True
    assert decision["investigation_casebook_manifest_sha256"] == APPROVED_CASEBOOK_SHA256
    assert decision["pre_finalization_candidate_manifest_sha256"] == PRE_FINALIZATION_CANDIDATE_SHA256
    assert decision["release_tag_name"] == RELEASE_TAG
    assert project["decision"] == "APPROVED_COMPLETE"
    assert project["project_implementation_complete"] is True
    assert project["project_b_complete"] is True
    assert project["cnd_02_status"] == "OPEN"
    assert project["threshold_boundary_density_status"] == "CONTROLLED_DEFERRED"


def test_owner_approval_and_integrity_attestations_are_bound() -> None:
    approval = _json("phase15_owner_approval_record.json")
    integrity = _json("final_integrity_attestation.json")
    assert approval["decision"] == "APPROVED"
    assert approval["pre_finalization_candidate_manifest_sha256"] == PRE_FINALIZATION_CANDIDATE_SHA256
    assert integrity["result"] == "PASS"
    assert integrity["phase_0_through_14_manifest_chain_unchanged"] is True
    assert integrity["part_a_working_tree_clean"] is True
    assert integrity["investigation_casebook_digest_stable"] is True
    assert integrity["alert_event_ledger_unchanged"] is True
    assert integrity["alert_event_ledger_sha256"] == APPROVED_ALERT_EVENT_LEDGER_SHA256
    assert integrity["monitoring_recalculated"] is False
    assert integrity["model_scored"] is False


def test_final_manifest_is_bound_and_finalizer_is_idempotent() -> None:
    first = finalize_phase15(ROOT)
    second = finalize_phase15(ROOT)
    assert first == second
    assert first == (REPORT / "manifest.sha256").read_text(encoding="ascii").strip()
    manifest = _json("manifest.json")
    assert manifest["status"] == "APPROVED_FROZEN"
    assert manifest["phase_15_complete"] is True
    assert manifest["project_b_complete"] is True
    assert manifest["pre_finalization_candidate_manifest_sha256"] == PRE_FINALIZATION_CANDIDATE_SHA256
    assert sha256_file(REPORT / "manifest.json") == first


def test_frozen_phase15_cannot_be_requalified_as_a_candidate() -> None:
    with pytest.raises(RuntimeError, match="approved and frozen"):
        run_phase15_qualification(ROOT)


def test_release_documentation_records_the_final_boundary() -> None:
    notes = (ROOT / "docs/RELEASE_NOTES_v1.0.0.md").read_text(encoding="utf-8")
    governance = (ROOT / "docs/GOVERNANCE.md").read_text(encoding="utf-8")
    assert "Status: `APPROVED_FROZEN`" in notes
    assert RELEASE_TAG in notes
    assert "Phase 15 and Project B implementation: complete" in notes
    assert "annotated tag and GitHub release are external publication evidence" in governance
