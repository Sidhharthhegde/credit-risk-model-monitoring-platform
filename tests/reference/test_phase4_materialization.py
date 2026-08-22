from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from credit_risk_monitoring.reference.materialization import _numeric_bin, _semantic_hash, _score_bins


def test_semantic_hash_is_copy_stable_and_value_sensitive() -> None:
    frame = pd.DataFrame({"a": [1.0, np.nan], "b": pd.Series(["x", None], dtype="string")})
    assert _semantic_hash(frame) == _semantic_hash(frame.copy(deep=True))
    changed = frame.copy()
    changed.loc[0, "a"] = 2.0
    assert _semantic_hash(frame) != _semantic_hash(changed)


def test_numeric_bins_collapse_duplicate_boundaries_and_keep_open_tails() -> None:
    definition = _numeric_bin("constant", pd.Series([1.0, 1.0, np.nan]))
    assert definition["actual_nonmissing_bins"] == 1
    assert definition["reason_for_reduction"] == "CONSTANT_REFERENCE_FEATURE"
    assert definition["lower_tail"] == "NEGATIVE_INFINITY"
    assert definition["upper_tail"] == "POSITIVE_INFINITY"
    assert definition["missing_bucket"] == "__MISSING__"


def test_score_bins_do_not_turn_threshold_into_a_bin() -> None:
    definition = _score_bins(np.linspace(0.01, 0.5, 100))
    assert definition["actual_bins"] == 10
    assert definition["threshold_01_is_bin_definition"] is False
    assert definition["optional_risk_bands_created"] is False


def test_phase4_candidate_preserves_review_gate_when_present() -> None:
    root = Path(__file__).resolve().parents[2]
    decision = root / "reports/reference/REFERENCE-MATERIALIZATION-01/phase4_completion_decision.json"
    if decision.exists():
        payload = json.loads(decision.read_text(encoding="utf-8"))
        assert payload["technical_qualification"] == "PASS"
        assert payload["review_decision"] in {"PENDING_USER_PROTOCOL_OWNER_REVIEW", "APPROVED"}
        assert payload["phase_4_complete"] is (payload["review_decision"] == "APPROVED")
        assert payload["monitoring_execution_authorized"] is False
