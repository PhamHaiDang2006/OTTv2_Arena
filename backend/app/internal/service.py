"""Worker callbacks (contracts/behavior.md "Worker, lease và callback").

- The job must exist and match the URL/payload resource and attempt.
- A terminal callback already stored: identical payload + same lease token → 200 (even after the lease is
  released); anything else → 409. A late `running`/`building` after terminal → 409, no event, no state change.
- Otherwise X-Worker-Lease must equal the current Redis lease `ottv2:lease:{job_id}`.
- Artifacts are finalized (copied from the worker's key to the canonical immutable key) before commit.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

import redis
from sqlalchemy.orm import Session

from app import storage as st
from app.audit import audit
from app.errors import ApiError, conflict, invalid, not_found
from app.idempotency import hash_json
from app.matches import service as matches
from app.models import CallbackReceipt, Game, Submission, WorkerJob
from app.queue import add_event, get_redis, lease_key, team_channel
from app.timeutil import utcnow

log = logging.getLogger('ottv2.callbacks')


def _job(db: Session, job_id: str, kind: str) -> WorkerJob:
    job = db.get(WorkerJob, uuid.UUID(job_id), with_for_update=True)
    if job is None or job.kind != kind:
        raise not_found('Không tìm thấy job')
    return job


def _replayed_terminal(db: Session, job: WorkerJob, lease: uuid.UUID, payload_hash: str) -> bool:
    receipt = db.get(CallbackReceipt, job.id)
    if receipt is None:
        return False
    if receipt.payload_hash == payload_hash and receipt.lease_token == lease:
        return True
    raise conflict(message='Job đã có kết quả cuối khác', reason='terminal_conflict')


def verify_lease(job: WorkerJob, lease: uuid.UUID) -> None:
    try:
        current = get_redis().get(lease_key(job.id))
    except redis.RedisError as exc:
        raise ApiError(503, 'SERVICE_UNAVAILABLE', 'Không kiểm tra được lease') from exc
    if current is None or current.decode() != str(lease):
        raise conflict(message='Lease không còn hiệu lực', reason='lease_mismatch')
    if job.lease_seen_at is None:
        job.lease_seen_at = utcnow()


def _finalize(source: str, target: str, required: bool = True) -> str | None:
    """Copy a worker-uploaded object to its canonical key; canonical keys are never overwritten."""
    storage = st.get_storage()
    try:
        src = storage.head(source)
        if src is None:
            if required:
                raise invalid('Artifact chưa được tải lên', reason='artifact_missing', key=source)
            return None
        if source != target:
            dst = storage.head(target)
            if dst is None:
                storage.copy(source, target)
            elif dst.get('ETag') != src.get('ETag') or dst.get('ContentLength') != src.get('ContentLength'):
                raise conflict(message='Artifact chuẩn đã tồn tại với nội dung khác', reason='artifact_conflict',
                               key=target)
    except st.StorageError as exc:
        raise st.unavailable(exc) from exc
    return target


def _finalize_logs(game_id: uuid.UUID, log_key: str | None, required: bool) -> str | None:
    """log_key is a prefix holding blue.stderr.log / red.stderr.log (architecture.md 5.3)."""
    if not log_key:
        return None
    prefix = log_key if log_key.endswith('/') else log_key + '/'
    target = st.log_prefix(str(game_id))
    for filename in st.STDERR_FILES.values():
        _finalize(prefix + filename, target + filename, required=required)
    return target


def _receipt(db: Session, job: WorkerJob, status: str, lease: uuid.UUID, payload_hash: str, outcome: str) -> None:
    now = utcnow()
    job.status, job.outcome, job.finished_at = 'terminal', outcome, now
    db.add(CallbackReceipt(job_id=job.id, status=status, payload_hash=payload_hash, lease_token=lease))


def handle_build(db: Session, submission_id: uuid.UUID, lease: uuid.UUID, body: dict[str, Any]) -> None:
    job = _job(db, body['job_id'], 'build')
    if job.submission_id != submission_id:
        raise conflict(message='Job không thuộc bản nộp này', reason='job_mismatch')
    payload_hash = hash_json(body)
    if _replayed_terminal(db, job, lease, payload_hash):
        return
    verify_lease(job, lease)
    submission = db.get(Submission, submission_id, with_for_update=True)
    status, now = body['status'], utcnow()
    if status == 'building':
        if submission.status == 'queued':
            submission.status, submission.updated_at = 'building', now
            job.status, job.started_at = 'running', now
            add_event(db, 'build.updated', team_channel(submission.team_id),
                      {'submission_id': str(submission.id), 'status': 'building'})
        elif submission.status != 'building':
            raise conflict(message='Bản nộp đã có kết quả build', reason='terminal_conflict')
        return
    if submission.status not in ('queued', 'building'):
        raise conflict(message='Bản nộp đã có kết quả build', reason='terminal_conflict')
    log_key = None
    if body['build_log_key']:
        log_key = _finalize(body['build_log_key'], st.build_log_key(str(submission.id)), required=status == 'ready')
    submission.status, submission.updated_at, submission.build_log_key = status, now, log_key
    if status == 'ready':
        submission.image_tag = body['image_tag']
        outcome = 'ready'
    else:
        submission.build_error = {'code': body['error']['code'], 'message': body['error']['message']}
        outcome = 'infra_error' if body['error']['code'] == 'INFRA_ERROR' else 'failed'
    if job.started_at is None:
        job.started_at = now
    _receipt(db, job, status, lease, payload_hash, outcome)
    add_event(db, 'build.updated', team_channel(submission.team_id),
              {'submission_id': str(submission.id), 'status': status})


def fail_attempt(db: Session, match, game: Game, error: dict[str, str], actor_reason: str) -> Game | None:
    """Record infra_error and create the next attempt (max 4 attempts), else leave the match blocked."""
    game.status, game.error, game.finished_at = 'infra_error', error, utcnow()
    db.flush()
    replacement = None
    if game.attempt < matches.MAX_AUTO_ATTEMPT:
        replacement = matches.new_attempt(db, match, game)
    else:
        audit(db, None, 'game.retries_exhausted', 'game', game.id,
              {'match_id': match.id, 'attempt': game.attempt, 'reason': actor_reason, 'error': error})
        log.error('Game %s exhausted automatic retries; match %s blocked', game.id, match.id)
    matches.progress(db, match)
    return replacement


def handle_game(db: Session, game_id: uuid.UUID, lease: uuid.UUID, body: dict[str, Any]) -> None:
    job = _job(db, body['job_id'], 'match')
    if job.game_id != game_id or job.attempt != body['attempt']:
        raise conflict(message='Job không khớp ván/attempt', reason='job_mismatch')
    payload_hash = hash_json(body)
    if _replayed_terminal(db, job, lease, payload_hash):
        return
    verify_lease(job, lease)
    game = db.get(Game, game_id)
    match = matches.get_match(db, game.match_id, lock=True)  # lock order: match, then game
    db.refresh(game, with_for_update=True)
    status, now = body['status'], utcnow()
    if status == 'running':
        if game.status == 'queued':
            game.status, game.started_at = 'running', now
            job.status, job.started_at = 'running', now
            if match.status == 'queued':
                match.status = 'running'
        elif game.status != 'running':
            raise conflict(message='Ván đã kết thúc', reason='terminal_conflict')
        return
    if game.status not in ('queued', 'running'):
        raise conflict(message='Ván đã kết thúc', reason='terminal_conflict')
    if job.started_at is None:
        job.started_at = now
    game.duration_ms = body['duration_ms']
    if status == 'finished':
        game.replay_key = _finalize(body['replay_key'], st.replay_key(str(game.id)))
        game.log_key = _finalize_logs(game.id, body['log_key'], required=True)
        result = body['result']
        game.status, game.winner, game.reason, game.total_plies = 'finished', result['winner'], result['reason'], result['plies']
        game.finished_at = now
        _receipt(db, job, status, lease, payload_hash, 'finished')
        db.flush()
        matches.emit(db, match, 'game.finished', {'game_id': str(game.id), 'match_id': str(match.id)})
        matches.progress(db, match)
        return
    game.log_key = _finalize_logs(game.id, body['log_key'], required=False)
    _receipt(db, job, status, lease, payload_hash, 'infra_error')
    fail_attempt(db, match, game, {'code': body['error']['code'], 'message': body['error']['message']}, 'callback')
