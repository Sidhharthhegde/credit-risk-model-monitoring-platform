"""Validated reader for the version-controlled Phase 15 investigation casebook."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from credit_risk_monitoring.qualification.binding import sha256_file


class CasebookBindingError(RuntimeError):
    pass


@dataclass(frozen=True)
class CasebookBundle:
    manifest: dict[str, Any]
    registry: dict[str, Any]
    cases: tuple[dict[str, Any], ...]


def load_casebook(project_root: Path) -> CasebookBundle:
    output = project_root / "reports/investigation/INVESTIGATION-CASEBOOK-01"
    manifest_path = output / "manifest.json"
    digest_path = output / "manifest.sha256"
    if not manifest_path.is_file() or not digest_path.is_file():
        raise CasebookBindingError("Investigation casebook candidate is not materialized")
    expected = digest_path.read_text(encoding="utf-8").strip()
    if sha256_file(manifest_path) != expected:
        raise CasebookBindingError("Investigation casebook manifest digest does not reconcile")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = {row["path"]: row for row in manifest["artifacts"]}
    required = ["case_registry.json", "INV-01.json", "INV-02.json", "INV-03.json", "INV-04.json"]
    for name in required:
        row = artifacts.get(name)
        path = output / name
        if row is None or not path.is_file() or sha256_file(path) != row["sha256"]:
            raise CasebookBindingError(f"Investigation casebook artifact does not reconcile: {name}")
    registry = json.loads((output / "case_registry.json").read_text(encoding="utf-8"))
    cases = tuple(json.loads((output / name).read_text(encoding="utf-8")) for name in required[1:])
    return CasebookBundle(manifest=manifest, registry=registry, cases=cases)
