"""Transactional outbox: worker jobs (RQ) and WebSocket events are written with the business change and
delivered after commit. A failed delivery stays pending and the scheduler retries it with the same job_id."""
from __future__ import annotations

import json
import logging
import uuid
from functools import lru_cache
from typing import Any

import redis
from rq import Queue
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import session_scope
from app.models import Outbox, QueueControl, WorkerJob
from app.timeutil import iso, utcnow

log = logging.getLogger('ottv2.queue')

ENTRYPOINTS = {'build': 'ottv2_runner.jobs.build_submission', 'match': 'ottv2_runner.jobs.run_match'}
EVENTS_CHANNEL = 'ottv2:ws:events'
_PENDING = 'ottv2_outbox_ids'


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, socket_timeout=5, socket_connect_timeout=5)


def lease_key(job_id: uuid.UUID | str) -> str:
    return f'ottv2:lease:{job_id}'


def _track(db: Session, entry: Outbox) -> None:
    db.add(entry)
    db.flush()
    db.info.setdefault(_PENDING, []).append(entry.id)


def add_job(db: Session, job: WorkerJob) -> WorkerJob:
    db.add(job)
    db.flush()
    _track(db, Outbox(kind='job', target=job.queue, job_id=job.id, payload=job.payload))
    return job


def add_event(db: Session, event_type: str, channel: str, data: dict[str, Any]) -> None:
    event = {'schema_version': 1, 'event_id': str(uuid.uuid4()), 'type': event_type, 'channel': channel,
             'occurred_at': iso(utcnow()), 'data': data}
    _track(db, Outbox(kind='event', target=channel, payload=event))


def team_channel(team_id: uuid.UUID | str) -> str:
    return f'team:{team_id}'


def enqueue(queue_name: str, job_id: uuid.UUID | str, payload: dict[str, Any]) -> None:
    settings = get_settings()
    kind = 'build' if queue_name == 'build' else 'match'
    timeout = settings.rq_build_timeout_seconds if kind == 'build' else settings.rq_match_timeout_seconds
    Queue(queue_name, connection=get_redis()).enqueue(
        ENTRYPOINTS[kind], payload, job_id=str(job_id), job_timeout=timeout, result_ttl=86400, failure_ttl=7 * 86400)


def publish_event(event: dict[str, Any]) -> None:
    get_redis().publish(EVENTS_CHANNEL, json.dumps(event, ensure_ascii=False))


def deliver(ids: list[int] | None = None, limit: int = 200) -> int:
    """Deliver pending outbox rows; SKIP LOCKED lets several processes run this safely."""
    delivered = 0
    with session_scope() as db:
        paused = set(db.scalars(select(QueueControl.name).where(QueueControl.paused)))
        query = select(Outbox).where(Outbox.delivered_at.is_(None)).order_by(Outbox.id).limit(limit)
        if ids is not None:
            query = query.where(Outbox.id.in_(ids))
        for entry in db.scalars(query.with_for_update(skip_locked=True)):
            if entry.kind == 'job' and entry.target in paused:
                continue
            try:
                if entry.kind == 'job':
                    enqueue(entry.target, entry.job_id, entry.payload)
                else:
                    publish_event(entry.payload)
            except Exception as exc:  # noqa: BLE001 - delivery is retried by the scheduler
                entry.attempts += 1
                entry.last_error = str(exc)[:500]
                log.warning('Outbox delivery failed id=%s: %s', entry.id, exc)
                continue
            entry.delivered_at = utcnow()
            delivered += 1
    return delivered


def commit(db: Session) -> None:
    """Commit, then try to deliver this transaction's outbox rows immediately (best effort)."""
    ids = db.info.pop(_PENDING, [])
    db.commit()
    if ids:
        try:
            deliver(ids)
        except Exception as exc:  # noqa: BLE001 - scheduler retries pending rows
            log.warning('Immediate outbox delivery failed: %s', exc)
