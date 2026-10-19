"""Idempotency-Key handling per contracts/behavior.md.

Scope = actor + method + normalized path + key, kept 24h. A transaction-scoped advisory lock serializes
requests with the same scope: a concurrent duplicate gets 409 REQUEST_IN_PROGRESS, a completed one replays
the stored status/body, a different body gets 409 IDEMPOTENCY_CONFLICT. The record is written in the same
transaction as the business change, so a rolled-back request leaves nothing behind.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.deps import uuid_header
from app.errors import conflict
from app.models import IdempotencyRecord
from app.timeutil import utcnow

RETENTION = timedelta(hours=24)


def hash_json(body: Any) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def hash_parts(*parts: bytes) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(hashlib.sha256(part).digest())
    return digest.hexdigest()


@dataclass
class Idempotency:
    db: Session
    actor_id: uuid.UUID
    method: str
    path: str
    key: uuid.UUID
    request_hash: str
    replay: JSONResponse | None = None

    def record(self, status: int, body: Any) -> JSONResponse:
        """Store the successful response in the current transaction; the caller commits."""
        self.db.add(IdempotencyRecord(actor_id=self.actor_id, method=self.method, path=self.path, key=self.key,
                                      request_hash=self.request_hash, response_status=status, response_body=body))
        return JSONResponse(body, status_code=status)


def _lock_id(*parts: str) -> int:
    digest = hashlib.sha256('|'.join(parts).encode('utf-8')).digest()
    return int.from_bytes(digest[:8], 'big', signed=True)


def begin(db: Session, request: Request, actor_id: uuid.UUID, request_hash: str) -> Idempotency:
    key = uuid_header(request, 'Idempotency-Key')
    method = request.method.upper()
    path = request.url.path.rstrip('/') or '/'
    if not db.scalar(select(func.pg_try_advisory_xact_lock(_lock_id(str(actor_id), method, path, str(key))))):
        raise conflict('REQUEST_IN_PROGRESS')
    scope = (IdempotencyRecord.actor_id == actor_id, IdempotencyRecord.method == method,
             IdempotencyRecord.path == path, IdempotencyRecord.key == key)
    cutoff = utcnow() - RETENTION
    db.execute(delete(IdempotencyRecord).where(*scope, IdempotencyRecord.created_at <= cutoff))
    existing = db.scalar(select(IdempotencyRecord).where(*scope))
    idem = Idempotency(db, actor_id, method, path, key, request_hash)
    if existing is not None:
        if existing.request_hash != request_hash:
            raise conflict('IDEMPOTENCY_CONFLICT')
        idem.replay = JSONResponse(existing.response_body, status_code=existing.response_status,
                                   headers={'Idempotent-Replay': 'true'})
    return idem


def purge_expired(db: Session) -> int:
    result = db.execute(delete(IdempotencyRecord).where(IdempotencyRecord.created_at <= utcnow() - RETENTION))
    return result.rowcount or 0
