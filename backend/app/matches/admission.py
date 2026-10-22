"""Scrimmage admission (contracts/behavior.md, contract 1.3.0).

Official games run on dedicated `match:tournament` workers; scrimmages run on their own small `match:scrimmage`
pool, whose size caps how many scrimmage games run at once. While tournament games are pending or running, or the
scrimmage backlog is full, new scrimmages are refused. Scrimmages accepted earlier are never cancelled, re-queued or
moved to tournament workers: they keep running on the scrimmage pool and their quota is not charged again.

The backlog threshold is soft: two teams admitted at the same moment may each add their games."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import ApiError
from app.models import Match, QueueControl, WorkerJob

# A blocked match waits for an admin rerun; it must not hold one of the team's slots forever.
ACTIVE_MATCH_STATUSES = ('queued', 'running')
PAUSE_MESSAGES = {
    'queue_paused': 'Ban tổ chức đang tạm dừng hàng đợi đánh tập. Hãy thử lại sau.',
    'tournament_load': 'Giải đấu đang chạy nên tạm dừng nhận trận đánh tập mới. Trận đã tạo vẫn chạy tiếp.',
    'scrimmage_backlog': 'Hàng đợi đánh tập đang đầy. Hãy thử lại sau ít phút; trận đã tạo vẫn chạy tiếp.',
}


def _jobs(db: Session, queue: str, *statuses: str) -> int:
    return db.scalar(select(func.count()).select_from(WorkerJob)
                     .where(WorkerJob.queue == queue, WorkerJob.status.in_(statuses))) or 0


def paused_reason(db: Session) -> str | None:
    settings = get_settings()
    control = db.get(QueueControl, 'match:scrimmage')
    if control is not None and control.paused:
        return 'queue_paused'
    threshold = settings.scrimmage_pause_tournament_jobs
    if threshold > 0 and _jobs(db, 'match:tournament', 'queued', 'running') >= threshold:
        return 'tournament_load'
    if _jobs(db, 'match:scrimmage', 'queued') >= settings.scrimmage_max_pending_games:
        return 'scrimmage_backlog'
    return None


def admission(db: Session) -> dict:
    reason = paused_reason(db)
    return {'accepting': reason is None, 'paused_reason': reason}


def active_matches(db: Session, team_id: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(Match).where(
        Match.stage == 'scrimmage', Match.created_by_team_id == team_id,
        Match.status.in_(ACTIVE_MATCH_STATUSES))) or 0


def ensure_can_create(db: Session, team_id: uuid.UUID) -> None:
    """Call with the team row locked, so the per-team count cannot race."""
    reason = paused_reason(db)
    if reason is not None:
        raise ApiError(503, 'SCRIMMAGE_PAUSED', PAUSE_MESSAGES[reason], {'reason': reason},
                       headers={'Retry-After': '60'})
    limit = get_settings().scrimmage_max_active_per_team
    active = active_matches(db, team_id)
    if active >= limit:
        raise ApiError(429, 'SCRIMMAGE_LIMIT', details={'active': active, 'active_limit': limit})
