"""Single-run lock with explicit, evidenced stale-lock recovery."""

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class LockError(RuntimeError):
    kind = "INVALID"


class ActiveLockError(LockError):
    kind = "ACTIVE"


class InvalidLockError(LockError):
    kind = "INVALID_OR_STALE"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ExecutionLock:
    path: Path
    execution_id: str
    maximum_age_seconds: int
    recovered_lock_path: str | None = None

    def acquire(self, *, recover_stale: bool = False, recovery_dir: Path | None = None) -> dict:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1.0.0",
            "execution_id": self.execution_id,
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "created_utc": _utc_now().isoformat(),
        }
        try:
            with self.path.open("x", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
            return payload
        except FileExistsError:
            pass

        existing = self._read_existing()
        age = (_utc_now() - datetime.fromisoformat(existing["created_utc"])).total_seconds()
        if age <= self.maximum_age_seconds:
            raise ActiveLockError(f"An active execution lock is present ({int(age)} seconds old)")
        if not recover_stale:
            raise InvalidLockError("A stale execution lock is present; explicit recovery is required")
        if recovery_dir is None:
            raise InvalidLockError("A recovery evidence directory is required")
        recovery_dir.mkdir(parents=True, exist_ok=True)
        recovered = recovery_dir / "recovered_stale_lock.json"
        recovery = {
            "recovered_utc": _utc_now().isoformat(),
            "recovered_by_execution_id": self.execution_id,
            "stale_lock": existing,
            "stale_age_seconds": int(age),
        }
        recovered.write_text(json.dumps(recovery, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.recovered_lock_path = str(recovered)
        self.path.unlink()
        try:
            with self.path.open("x", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
        except FileExistsError as exc:
            raise ActiveLockError("Another execution acquired the lock during stale recovery") from exc
        return payload

    def _read_existing(self) -> dict:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not all(key in payload for key in ("execution_id", "created_utc", "pid", "host")):
                raise ValueError("missing required fields")
            parsed = datetime.fromisoformat(str(payload["created_utc"]))
            if parsed.tzinfo is None:
                raise ValueError("timestamp has no timezone")
            return payload
        except Exception as exc:
            raise InvalidLockError("Execution lock is corrupt or invalid") from exc

    def release(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        if payload.get("execution_id") == self.execution_id:
            self.path.unlink()
