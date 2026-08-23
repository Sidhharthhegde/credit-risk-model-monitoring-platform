from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StageResult:
    stage_id: str
    status: str
    detail: str


@dataclass(frozen=True)
class OrchestrationResult:
    mode: str
    status: str
    stages: tuple[StageResult, ...]
    output_root: Path | None
