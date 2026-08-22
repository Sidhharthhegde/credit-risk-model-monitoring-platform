"""Load and verify the single authoritative Part A binding contract."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class BindingContractError(ValueError):
    """Raised when the frozen Part A binding cannot be trusted or resolved."""


@dataclass(frozen=True)
class ArtifactExpectation:
    role: str
    relative_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class PartABinding:
    contract_path: Path
    payload: dict[str, Any]
    artifacts: tuple[ArtifactExpectation, ...]

    @property
    def model(self) -> dict[str, Any]:
        return self.payload["model"]

    @property
    def part_a(self) -> dict[str, Any]:
        return self.payload["part_a"]

    @property
    def threshold(self) -> dict[str, Any]:
        return self.payload["threshold"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise BindingContractError(f"Binding field {key!r} must be an object")
    return value


def load_binding(path: str | Path) -> PartABinding:
    contract_path = Path(path).resolve()
    if not contract_path.is_file():
        raise BindingContractError(f"Binding contract does not exist: {contract_path.name}")
    try:
        payload = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BindingContractError("Binding contract is not valid readable JSON") from exc
    if not isinstance(payload, dict):
        raise BindingContractError("Binding contract root must be an object")

    part_a = _require_mapping(payload, "part_a")
    model = _require_mapping(payload, "model")
    threshold = _require_mapping(payload, "threshold")
    required_part_a = {
        "repository",
        "published_commit",
        "runtime_root_environment_variable",
        "workspace_mutability",
    }
    required_model = {
        "development_freeze_id",
        "model_id",
        "model_version",
        "artifact_relative_path",
        "artifact_size_bytes",
        "artifact_sha256",
        "raw_predictor_count",
        "encoded_predictor_count",
        "positive_class",
        "probability_representation",
    }
    required_threshold = {"threshold_id", "value", "operator"}
    for name, mapping, required in (
        ("part_a", part_a, required_part_a),
        ("model", model, required_model),
        ("threshold", threshold, required_threshold),
    ):
        missing = required - set(mapping)
        if missing:
            raise BindingContractError(f"Binding {name} is missing: {sorted(missing)}")

    raw_artifacts = payload.get("authoritative_artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        raise BindingContractError("Binding authoritative_artifacts must be a non-empty list")
    model_expectation = ArtifactExpectation(
        role="MODEL_ARTIFACT",
        relative_path=str(model["artifact_relative_path"]),
        size_bytes=int(model["artifact_size_bytes"]),
        sha256=str(model["artifact_sha256"]),
    )
    artifacts = [model_expectation]
    for item in raw_artifacts:
        if not isinstance(item, dict):
            raise BindingContractError("Every authoritative artifact must be an object")
        try:
            artifacts.append(
                ArtifactExpectation(
                    role=str(item["role"]),
                    relative_path=str(item["relative_path"]),
                    size_bytes=int(item["size_bytes"]),
                    sha256=str(item["sha256"]),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise BindingContractError("Authoritative artifact fields are invalid") from exc
    roles = [item.role for item in artifacts]
    paths = [Path(item.relative_path).as_posix().casefold() for item in artifacts]
    if len(set(roles)) != len(roles):
        raise BindingContractError("Binding contains duplicate artifact roles")
    if len(set(paths)) != len(paths):
        raise BindingContractError("Binding contains duplicate or ambiguous artifact paths")
    for item in artifacts:
        if len(item.sha256) != 64 or any(c not in "0123456789abcdef" for c in item.sha256):
            raise BindingContractError(f"Invalid SHA-256 for {item.role}")
        relative = Path(item.relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise BindingContractError(f"Unsafe relative artifact path for {item.role}")
    return PartABinding(contract_path, payload, tuple(artifacts))


def resolve_part_a_root(binding: PartABinding, explicit_root: str | Path | None = None) -> Path:
    environment_name = str(binding.part_a["runtime_root_environment_variable"])
    configured = explicit_root if explicit_root is not None else os.environ.get(environment_name)
    if not configured:
        raise BindingContractError(f"Part A root is not configured through {environment_name}")
    root = Path(configured).resolve()
    if not root.is_dir():
        raise BindingContractError("Configured Part A root does not exist")
    return root


def resolve_artifact(root: Path, expectation: ArtifactExpectation) -> Path:
    resolved = (root / expectation.relative_path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise BindingContractError(f"Artifact escapes Part A root: {expectation.role}") from exc
    return resolved


def verify_artifacts(binding: PartABinding, root: Path) -> tuple[list[dict[str, Any]], bool]:
    records: list[dict[str, Any]] = []
    for expectation in binding.artifacts:
        path = resolve_artifact(root, expectation)
        exists = path.is_file()
        observed_size = path.stat().st_size if exists else None
        observed_hash = sha256_file(path) if exists else None
        size_match = observed_size == expectation.size_bytes
        hash_match = observed_hash == expectation.sha256
        records.append(
            {
                "artifact_identity": expectation.role,
                "relative_path": Path(expectation.relative_path).as_posix(),
                "expected_size_bytes": expectation.size_bytes,
                "observed_size_bytes": observed_size,
                "size_match": size_match,
                "expected_sha256": expectation.sha256,
                "observed_sha256": observed_hash,
                "hash_match": hash_match,
                "result": "PASS" if exists and size_match and hash_match else "FAIL",
            }
        )
    return records, all(record["result"] == "PASS" for record in records)

