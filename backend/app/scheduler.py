"""Background loop (`python -m app.cli scheduler`): outbox delivery, lease watchdog, scheduled freeze,
similarity after freeze, cleanup. Safe to run in several processes (row locks with SKIP LOCKED)."""
from __future__ import annotations

import logging
import signal
import time
from datetime import timedelta

import redis
from rq.job import Job
from sqlalchemy import delete, select

from app import queue
from app.audit import audit
from app.db import session_scope
from app.errors import ApiError
from app.idempotency import purge_expired
from app.internal.service import fail_attempt
from app.matches import service as matches
from app.models import AuditLog, Game, Outbox, QueueControl, RefreshToken, Round, RoundSnapshot, Submission, WorkerJob
from app.public.router import tournament_enabled
from app.timeutil import utcnow

log = logging.getLogger('ottv2.scheduler')
REDELIVER_AFTER = timedelta(minutes=5)
LOST_WORKER = {'code': 'INFRA_ERROR', 'message': 'Worker mất lease trước khi gửi kết quả'}


def watchdog_once() -> int:
    """Claimed jobs whose lease vanished before a terminal callback become infra_error (new attempt for games).
    Jobs never claimed are not touched (queued work is not a lost game)."""
    handled = 0
    client = queue.get_redis()
    now = utcnow()
    with session_scope() as db:
        paused = set(db.scalars(select(QueueControl.name).where(QueueControl.paused)))
        jobs = db.scalars(select(WorkerJob).where(WorkerJob.status != 'terminal').order_by(WorkerJob.created_at)
                          .with_for_update(skip_locked=True)).all()
        for job in jobs:
            try:
                alive = client.exists(queue.lease_key(job.id))
            except redis.RedisError as exc:
                log.warning('Watchdog cannot reach Redis: %s', exc)
                return handled
            if alive:
                if job.lease_seen_at is None:
                    job.lease_seen_at = now
                if job.status == 'queued':
                    job.status, job.started_at = 'running', job.started_at or now
                continue
            if job.lease_seen_at is None and job.status == 'queued':
                if _rq_gave_up(client, job):
                    _lost(db, job)  # the RQ worker died/failed before the watchdog ever saw a lease
                    handled += 1
                elif job.queue not in paused and now - job.created_at > REDELIVER_AFTER:
                    _redeliver_if_lost(db, client, job)
                continue
            _lost(db, job)
            handled += 1
    return handled


def _rq_gave_up(client, job: WorkerJob) -> bool:
    try:
        rq_job = Job.fetch(str(job.id), connection=client)
    except Exception:  # noqa: BLE001 - missing job: handled by redelivery
        return False
    return rq_job.get_status(refresh=False) in ('failed', 'stopped', 'canceled')


def _redeliver_if_lost(db, client, job: WorkerJob) -> None:
    """Redis lost the RQ job (e.g. restart without persistence): deliver again with the same job_id."""
    if Job.exists(str(job.id), connection=client):
        return
    entry = db.scalar(select(Outbox).where(Outbox.job_id == job.id, Outbox.kind == 'job'))
    if entry is not None and entry.delivered_at is not None:
        entry.delivered_at = None
        log.warning('Re-delivering job %s missing from Redis', job.id)


def _lost(db, job: WorkerJob) -> None:
    now = utcnow()
    job.status, job.outcome, job.finished_at = 'terminal', 'infra_error', now
    if job.kind == 'build':
        submission = db.get(Submission, job.submission_id, with_for_update=True)
        if submission.status in ('queued', 'building'):
            submission.status, submission.updated_at, submission.build_error = 'failed', now, dict(LOST_WORKER)
            queue.add_event(db, 'build.updated', queue.team_channel(submission.team_id),
                            {'submission_id': str(submission.id), 'status': 'failed'})
        return
    game = db.get(Game, job.game_id)
    match = matches.get_match(db, game.match_id, lock=True)
    db.refresh(game, with_for_update=True)
    if game.status in ('queued', 'running'):
        log.warning('Lease lost for game %s attempt %s', game.id, game.attempt)
        fail_attempt(db, match, game, dict(LOST_WORKER), 'lease_expired')


def scheduled_freeze_once() -> int:
    if not tournament_enabled():
        return 0
    from app.tournament.service import freeze_round, lock_round
    frozen = 0
    with session_scope() as db:
        due = list(db.scalars(select(Round.id).where(Round.status == 'draft', Round.freeze_at <= utcnow())))
    for round_id in due:
        with session_scope() as db:
            row = lock_round(db, round_id)  # tournament → round, same order as the admin endpoint
            if row.status != 'draft' or row.freeze_at is None or row.freeze_at > utcnow():
                continue
            try:
                with db.begin_nested():
                    freeze_round(db, None, row, 'scheduled', scheduled=True)
                frozen += 1
            except ApiError as exc:
                if row.freeze_failure_logged_for != row.freeze_at:
                    audit(db, None, 'round.freeze.rejected', 'round', row.id,
                          {'scheduled': True, 'error_code': exc.code, 'details': exc.details})
                    row.freeze_failure_logged_for = row.freeze_at
    return frozen


def similarity_once() -> int:
    from app.similarity import compute_for_snapshot
    done = 0
    with session_scope() as db:
        computed = select(AuditLog.target_id).where(AuditLog.action == 'similarity.computed')
        pending = db.scalars(select(RoundSnapshot.id).where(RoundSnapshot.id.not_in(computed))).all()
    for snapshot_id in pending:
        try:
            compute_for_snapshot(snapshot_id)
            done += 1
        except Exception as exc:  # noqa: BLE001 - retried next tick
            log.warning('Similarity for snapshot %s failed: %s', snapshot_id, exc)
    return done


def cleanup_once() -> None:
    with session_scope() as db:
        purge_expired(db)
        db.execute(delete(RefreshToken).where(RefreshToken.expires_at < utcnow() - timedelta(days=30)))


def run(stop_after: float | None = None) -> None:
    running = True

    def _stop(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    tasks = [(2, queue.deliver), (15, watchdog_once), (15, scheduled_freeze_once), (60, similarity_once),
             (3600, cleanup_once)]
    last = {fn: 0.0 for _, fn in tasks}
    started = time.monotonic()
    log.info('Scheduler started')
    while running and (stop_after is None or time.monotonic() - started < stop_after):
        for interval, fn in tasks:
            if time.monotonic() - last[fn] >= interval:
                last[fn] = time.monotonic()
                try:
                    fn()
                except Exception:  # noqa: BLE001 - keep the loop alive
                    log.exception('Scheduler task %s failed', fn.__name__)
        time.sleep(0.5)
    log.info('Scheduler stopped')
