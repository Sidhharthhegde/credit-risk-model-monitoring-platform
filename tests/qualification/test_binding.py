from __future__ import annotations

import json
from pathlib import Path

import pytest

from credit_risk_monitoring.qualification.binding import (
    BindingContractError,
    load_binding,
    resolve_part_a_root,
    verify_artifacts,
)


def _payload() -> dict:
    return {
        "part_a": {
            "repository": "https://example.invalid/part-a",
            "published_commit": "a" * 40,
            "runtime_root_environment_variable": "PART_A_ROOT",
            "workspace_mutability": "READ_ONLY",
        },
        "model": {
            "development_freeze_id": "DF-01",
            "model_id": "XGBT-01",
            "model_version": "v1",
            "artifact_relative_path": "model.bin",
            "artifact_size_bytes": 1,
            "artifact_sha256": "0" * 64,
            "raw_predictor_count": 176,
            "encoded_predictor_count": 306,
            "positive_class": 1,
            "probability_representation": "RAW",
        },
        "threshold": {"threshold_id": "THRESHOLD-01", "value": 0.08, "operator": ">="},
        "authoritative_artifacts": [
            {"role": "SCHEMA", "relative_path": "schema.csv", "size_bytes": 1, "sha256": "0" * 64}
        ],
    }


def test_valid_binding_loads(tmp_path: Path) -> None:
    path = tmp_path / "binding.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")
    binding = load_binding(path)
    assert binding.model["model_id"] == "XGBT-01"
    assert len(binding.artifacts) == 2


def test_missing_required_identity_fails(tmp_path: Path) -> None:
    payload = _payload()
    del payload["model"]["model_id"]
    path = tmp_path / "binding.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(BindingContractError, match="missing"):
        load_binding(path)


def test_duplicate_artifact_path_fails(tmp_path: Path) -> None:
    payload = _payload()
    payload["authoritative_artifacts"][0]["relative_path"] = "model.bin"
    path = tmp_path / "binding.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(BindingContractError, match="duplicate or ambiguous"):
        load_binding(path)


def test_root_must_be_configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "binding.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")
    monkeypatch.delenv("PART_A_ROOT", raising=False)
    with pytest.raises(BindingContractError, match="not configured"):
        resolve_part_a_root(load_binding(path))


def test_hash_mismatch_fails_verification(tmp_path: Path) -> None:
    payload = _payload()
    (tmp_path / "model.bin").write_bytes(b"x")
    (tmp_path / "schema.csv").write_bytes(b"y")
    path = tmp_path / "binding.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    records, passed = verify_artifacts(load_binding(path), tmp_path)
    assert not passed
    assert all(record["result"] == "FAIL" for record in records)

