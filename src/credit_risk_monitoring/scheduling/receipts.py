"""Aggregate-only JSON receipt and JSONL event-log helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


class AggregateEventLog:
    def __init__(self, path: Path, execution_id: str) -> None:
        self.path = path
        self.execution_id = execution_id
        self.failure: dict[str, str] | None = None

    def _append(self, record: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def write(self, stage: str, severity: str, message: str) -> bool:
        """Append one aggregate event without allowing logging I/O to escape.

        Failure is retained for the runner's terminal receipt and exit-code
        reconciliation. This keeps exception handlers from being interrupted by
        a secondary logging failure.
        """
        record = {
            "execution_id": self.execution_id,
            "message": message,
            "severity": severity,
            "stage": stage,
            "utc": utc_now(),
        }
        try:
            self._append(record)
            return True
        except Exception as exc:  # logging must never mask the governed terminal state
            if self.failure is None:
                self.failure = {"type": type(exc).__name__, "message": str(exc)[:500]}
            return False
