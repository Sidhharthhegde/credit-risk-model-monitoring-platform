"""Hash-verify and import the frozen Part A feature functions read-only."""

from __future__ import annotations

import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from credit_risk_monitoring.qualification.binding import sha256_file


class FrozenPartAImportError(RuntimeError):
    """Raised when the configured Part A implementation cannot be trusted."""


@dataclass(frozen=True)
class FrozenPartAFeatureFunctions:
    build_bureau_features: Callable[..., Any]
    build_previous_application_features: Callable[..., Any]
    apply_deterministic_transformations: Callable[..., Any]
    integrate_master_dataset: Callable[..., Any]
    verified_sources: tuple[dict[str, object], ...]


def load_frozen_part_a_functions(
    part_a_root: Path,
    adapter_contract_path: Path,
) -> FrozenPartAFeatureFunctions:
    contract = json.loads(adapter_contract_path.read_text(encoding="utf-8"))
    records: list[dict[str, object]] = []
    for specification in contract["frozen_part_a_implementations"]:
        relative = Path(specification["relative_path"])
        path = (part_a_root / relative).resolve()
        try:
            path.relative_to(part_a_root.resolve())
        except ValueError as exc:
            raise FrozenPartAImportError("Frozen source path escapes Part A root") from exc
        if not path.is_file():
            raise FrozenPartAImportError(f"Frozen Part A source is missing: {relative.as_posix()}")
        observed = sha256_file(path)
        if observed != specification["sha256"]:
            raise FrozenPartAImportError(f"Frozen Part A source hash mismatch: {relative.as_posix()}")
        records.append(
            {
                "relative_path": relative.as_posix(),
                "sha256": observed,
                "function": specification["function"],
                "verified": True,
            }
        )

    root_text = str(part_a_root.resolve())
    sys.path[:] = [entry for entry in sys.path if str(Path(entry or ".").resolve()) != root_text]
    sys.path.insert(0, root_text)
    sys.dont_write_bytecode = True
    existing_src = sys.modules.get("src")
    if existing_src is not None:
        locations = [Path(value).resolve() for value in getattr(existing_src, "__path__", [])]
        if not locations or part_a_root.resolve() / "src" not in locations:
            raise FrozenPartAImportError("A non-Part-A src package is already loaded")
    modules = {
        "bureau": importlib.import_module("src.features.bureau_features"),
        "previous": importlib.import_module("src.features.previous_application_features"),
        "deterministic": importlib.import_module("src.features.deterministic"),
        "integration": importlib.import_module("src.features.integrate_all_features"),
    }
    expected_modules = {
        "bureau": part_a_root / "src" / "features" / "bureau_features.py",
        "previous": part_a_root / "src" / "features" / "previous_application_features.py",
        "deterministic": part_a_root / "src" / "features" / "deterministic.py",
        "integration": part_a_root / "src" / "features" / "integrate_all_features.py",
    }
    for name, module in modules.items():
        observed_module_path = Path(module.__file__).resolve()
        if observed_module_path != expected_modules[name].resolve():
            raise FrozenPartAImportError(
                f"Imported {name} module does not resolve to the hash-verified Part A path"
            )
    return FrozenPartAFeatureFunctions(
        build_bureau_features=modules["bureau"].build_bureau_features,
        build_previous_application_features=modules["previous"].build_previous_application_features,
        apply_deterministic_transformations=modules["deterministic"].apply_deterministic_transformations,
        integrate_master_dataset=modules["integration"].integrate_master_dataset,
        verified_sources=tuple(records),
    )
