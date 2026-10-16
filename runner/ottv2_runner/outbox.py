from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SAFE = re.compile(r"^[a-zA-Z0-9_-]+$")


@dataclass(frozen=True)
class PendingCallback:
    job_id: str
    lease_token: str
    url: str
    payload: dict[str, Any]


class CallbackOutbox:
    """File-backed durable queue; RUNNER_OUTBOX_DIR must be a persistent volume."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.completed_dir = directory / "completed"
        self.completed_dir.mkdir(parents=True, exist_ok=True)

    def _completed_path(self, job_id: str) -> Path:
        if not _SAFE.fullmatch(job_id):
            raise ValueError("Invalid job id for callback outbox")
        return self.completed_dir / f"{job_id}.terminal.json"

    def _stage_path(self, job_id: str, status: str) -> Path:
        if not _SAFE.fullmatch(job_id) or not _SAFE.fullmatch(status):
            raise ValueError("Invalid job id/status for callback outbox")
        return self.directory / f"{job_id}.{status}.json"

    def _stage_completed_path(self, job_id: str, status: str) -> Path:
        if not _SAFE.fullmatch(job_id) or not _SAFE.fullmatch(status):
            raise ValueError("Invalid job id/status for callback outbox")
        return self.completed_dir / f"{job_id}.{status}.json"

    def _atomic_write(self, path: Path, data: bytes) -> None:
        temp = path.with_suffix(".writing")
        descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def get(self, job_id: str) -> PendingCallback | None:
        paths = sorted(self.directory.glob(f"{job_id}.*.json"))
        if not paths:
            return None
        path = paths[0]
        raw = json.loads(path.read_text(encoding="utf-8"))
        return PendingCallback(raw["job_id"], raw["lease_token"], raw["url"], raw["payload"])

    def is_completed(self, job_id: str) -> bool:
        return self._completed_path(job_id).exists()

    def put(self, item: PendingCallback) -> None:
        path = self._stage_path(item.job_id, str(item.payload.get("status", "unknown")))
        data = json.dumps(
            {"job_id": item.job_id, "lease_token": item.lease_token, "url": item.url, "payload": item.payload},
            separators=(",", ":"), sort_keys=True,
        ).encode("utf-8")
        self._atomic_write(path, data)

    def mark_completed(self, item: PendingCallback) -> None:
        status = str(item.payload.get("status", "unknown"))
        source = self._stage_path(item.job_id, status)
        if source.exists():
            target = (
                self._completed_path(item.job_id)
                if status in {"ready", "failed", "finished", "infra_error"}
                else self._stage_completed_path(item.job_id, status)
            )
            data = json.dumps({"job_id": item.job_id, "status": status}, separators=(",", ":")).encode()
            self._atomic_write(target, data)
            source.unlink(missing_ok=True)

    def pending(self) -> list[PendingCallback]:
        result = []
        for path in sorted(self.directory.glob("*.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            result.append(PendingCallback(raw["job_id"], raw["lease_token"], raw["url"], raw["payload"]))
        return result
