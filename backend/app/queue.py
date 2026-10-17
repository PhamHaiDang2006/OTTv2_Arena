"""Transactional outbox: worker jobs (RQ) and WebSocket events are written with the business change and
delivered after commit. A failed delivery stays pending and the scheduler retries it with the same job_id.

Job delivery is idempotent against RQ's actual state: a job already waiting in its RQ queue, running or done is
only marked delivered, never pushed twice. That lets pausing a queue mark rows pending *before* pulling jobs out
of RQ, so a crash halfway through can never strand a job (see `drain`)."""
from __future__ import annotations

import json
import logging
import uuid
from functools import lru_cache
from typing import Any

import redis
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job
from sqlalchemy import or_, select, update
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


def rq_state(client: redis.Redis, queue_name: str, job_id: uuid.UUID | str) -> str:
    """'waiting' (in the RQ queue list), 'active' (started, finished, failed... RQ does not need it again) or
    'orphan' (unknown to RQ, or its hash says queued but it is in no queue list, e.g. removed by a drain)."""
    if client.lpos(Queue(queue_name, connection=client).key, str(job_id)) is not None:
        return 'waiting'
    try:
        status = Job.fetch(str(job_id), connection=client).get_status(refresh=False)
    except NoSuchJobError:
        return 'orphan'
    return 'orphan' if status in (None, 'queued') else 'active'


def _deliver_job(db: Session, entry: Outbox) -> None:
    job = db.get(WorkerJob, entry.job_id)
    if job is None or job.status == 'terminal':
        return
    if rq_state(get_redis(), entry.target, entry.job_id) == 'orphan':
        enqueue(entry.target, entry.job_id, entry.payload)


def deliver(ids: list[int] | None = None, limit: int = 200) -> int:
    """Deliver pending outbox rows; SKIP LOCKED lets several processes run this safely. Rows of paused queues
    are excluded in SQL, before LIMIT, so they can never starve other queues or events."""
    delivered = 0
    with session_scope() as db:
        paused = list(db.scalars(select(QueueControl.name).where(QueueControl.paused)))
        query = select(Outbox).where(Outbox.delivered_at.is_(None))
        if paused:
            query = query.where(or_(Outbox.kind != 'job', Outbox.target.not_in(paused)))
        if ids is not None:
            query = query.where(Outbox.id.in_(ids))
        query = query.order_by(Outbox.id).limit(limit)
        for entry in db.scalars(query.with_for_update(skip_locked=True)):
            try:
                if entry.kind == 'job':
                    _deliver_job(db, entry)
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


def drain(queue_name: str) -> int:
    """Take not-yet-claimed jobs back out of a paused RQ queue. Their outbox rows are marked pending and committed
    first; only then are the jobs removed. If Redis or the process fails in between, the leftovers are either
    still in RQ (delivery later recognises them and does not push them again) or removed with a pending row
    (re-enqueued on resume). Safe to repeat; the scheduler re-runs it for paused queues."""
    client = get_redis()
    rq_queue = Queue(queue_name, connection=client)
    ids = [x.decode() if isinstance(x, bytes) else x for x in client.lrange(rq_queue.key, 0, -1)]
    candidates = [job_id for job_id in ids if not client.exists(lease_key(job_id))]
    if not candidates:
        return 0
    with session_scope() as db:
        db.execute(update(Outbox).where(Outbox.kind == 'job', Outbox.job_id.in_([uuid.UUID(x) for x in candidates]))
                   .values(delivered_at=None))
    return sum(1 for job_id in candidates if rq_queue.remove(job_id))


def commit(db: Session) -> None:
    """Commit, then try to deliver this transaction's outbox rows immediately (best effort)."""
    ids = db.info.pop(_PENDING, [])
    db.commit()
    if ids:
        try:
            deliver(ids)
        except Exception as exc:  # noqa: BLE001 - scheduler retries pending rows
            log.warning('Immediate outbox delivery failed: %s', exc)
