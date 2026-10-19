"""Relational schema owned by backend (C). HTTP DTOs live in contracts/, not here.

Enum-like columns are VARCHAR + CHECK so contract enums stay readable in SQL and migrations.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {
    'ix': 'ix_%(table_name)s_%(column_0_N_name)s',
    'uq': 'uq_%(table_name)s_%(column_0_N_name)s',
    'ck': 'ck_%(table_name)s_%(constraint_name)s',
    'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
    'pk': 'pk_%(table_name)s',
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def _enum(column: str, values: tuple[str, ...], name: str | None = None) -> CheckConstraint:
    quoted = ', '.join(f"'{v}'" for v in values)
    return CheckConstraint(f'{column} IN ({quoted})', name=name or column)


def _id() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


USER_ROLES = ('member', 'captain', 'admin')
TEAM_STATUSES = ('pending', 'approved', 'disqualified')
LANGUAGES = ('python', 'cpp', 'java', 'node')
SUBMISSION_STATUSES = ('queued', 'building', 'ready', 'failed')
SCOPES = ('scrimmage', 'tournament')
TOURNAMENT_STATUSES = ('draft', 'drawn', 'running', 'finished')
ROUND_STATUSES = ('draft', 'frozen', 'running', 'finished')
STAGES = ('scrimmage', 'group', 'quarterfinal', 'semifinal', 'third_place', 'final')
ROUND_STAGES = STAGES[1:]
KNOCKOUT_STAGES = STAGES[2:]
BEST_OF = ('two_games', 'first_to_2', 'first_to_3')
MATCH_STATUSES = ('queued', 'running', 'finished', 'blocked')
GAME_STATUSES = ('queued', 'running', 'finished', 'infra_error')
SIDES = ('BLUE', 'RED')
REASONS = ('GOAL', 'WIPEOUT', 'STALEMATE', 'TIMEOUT', 'ILLEGAL_MOVE', 'CRASH', 'MOVE_LIMIT')
QUEUES = ('build', 'match:tournament', 'match:scrimmage')
JOB_STATUSES = ('queued', 'running', 'terminal')


class User(Base):
    __tablename__ = 'users'
    id: Mapped[uuid.UUID] = _id()
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default='member')
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = _now()
    __table_args__ = (
        _enum('role', USER_ROLES),
        Index('uq_users_email_lower', func.lower(email), unique=True),
    )


class Team(Base):
    __tablename__ = 'teams'
    id: Mapped[uuid.UUID] = _id()
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default='pending')
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    seed: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _now()
    __table_args__ = (
        _enum('status', TEAM_STATUSES),
        CheckConstraint('seed IS NULL OR seed >= 1', name='seed_positive'),
        Index('uq_teams_seed', 'seed', unique=True, postgresql_where=text('seed IS NOT NULL')),
    )


class TeamMember(Base):
    """One team per user (User.team_id in the contract is a single value)."""
    __tablename__ = 'team_members'
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('teams.id', ondelete='CASCADE'), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True, unique=True)
    created_at: Mapped[datetime] = _now()


class Submission(Base):
    __tablename__ = 'submissions'
    id: Mapped[uuid.UUID] = _id()
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('teams.id'), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id'))
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    source_key: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_manifest: Mapped[list] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default='queued')
    build_log_key: Mapped[str | None] = mapped_column(Text)
    image_tag: Mapped[str | None] = mapped_column(Text)
    build_error: Mapped[dict | None] = mapped_column(JSONB)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    submitted_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()
    __table_args__ = (
        _enum('language', LANGUAGES),
        _enum('status', SUBMISSION_STATUSES),
        CheckConstraint("status <> 'ready' OR image_tag IS NOT NULL", name='ready_has_image'),
        Index('ix_submissions_team_submitted', 'team_id', text('submitted_at DESC')),
    )


class ActiveBot(Base):
    __tablename__ = 'active_bots'
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('teams.id', ondelete='CASCADE'), primary_key=True)
    scope: Mapped[str] = mapped_column(String(16), primary_key=True)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('submissions.id'), nullable=False)
    updated_at: Mapped[datetime] = _now()
    __table_args__ = (_enum('scope', SCOPES),)


class Tournament(Base):
    __tablename__ = 'tournaments'
    id: Mapped[uuid.UUID] = _id()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default='draft')
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    ruleset_id: Mapped[str] = mapped_column(String(32), nullable=False)
    draw_seed: Mapped[int | None] = mapped_column(BigInteger)
    draw_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = _now()
    __table_args__ = (_enum('status', TOURNAMENT_STATUSES),)


class Group(Base):
    __tablename__ = 'groups'
    id: Mapped[uuid.UUID] = _id()
    tournament_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('tournaments.id', ondelete='CASCADE'), nullable=False)
    label: Mapped[str] = mapped_column(String(1), nullable=False)
    __table_args__ = (UniqueConstraint('tournament_id', 'label'), _enum('label', ('A', 'B', 'C', 'D')))


class GroupTeam(Base):
    __tablename__ = 'group_teams'
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('groups.id', ondelete='CASCADE'), primary_key=True)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('teams.id'), primary_key=True)
    pot: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (UniqueConstraint('group_id', 'pot'),)


class Round(Base):
    __tablename__ = 'rounds'
    id: Mapped[uuid.UUID] = _id()
    tournament_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('tournaments.id', ondelete='CASCADE'), nullable=False)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default='draft')
    freeze_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Last scheduled-freeze failure already audited for this freeze_at (avoids one audit row per tick).
    freeze_failure_logged_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()
    __table_args__ = (UniqueConstraint('tournament_id', 'stage'), _enum('stage', ROUND_STAGES), _enum('status', ROUND_STATUSES))


class RoundSnapshot(Base):
    __tablename__ = 'round_snapshots'
    id: Mapped[uuid.UUID] = _id()
    round_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('rounds.id', ondelete='CASCADE'), nullable=False, unique=True)
    frozen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id'))


class FrozenBot(Base):
    __tablename__ = 'frozen_bots'
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('round_snapshots.id', ondelete='CASCADE'), primary_key=True)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('teams.id'), primary_key=True)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('submissions.id'), nullable=False)


class Match(Base):
    __tablename__ = 'matches'
    id: Mapped[uuid.UUID] = _id()
    tournament_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('tournaments.id', ondelete='CASCADE'))
    round_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('rounds.id', ondelete='CASCADE'))
    group_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('groups.id'))
    bracket_code: Mapped[str | None] = mapped_column(String(8))  # QF1..QF4, SF1, SF2, F, TP
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    team_a_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('teams.id'), nullable=False)
    team_b_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('teams.id'), nullable=False)
    best_of: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default='queued')
    winner_team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('teams.id'))
    score_a: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_b: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overridden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('teams.id'))
    created_at: Mapped[datetime] = _now()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        _enum('stage', STAGES),
        _enum('best_of', BEST_OF),
        _enum('status', MATCH_STATUSES),
        CheckConstraint('team_a_id <> team_b_id', name='distinct_teams'),
        CheckConstraint("(stage = 'scrimmage') = (tournament_id IS NULL)", name='scrimmage_has_no_tournament'),
        Index('ix_matches_stage_status', 'stage', 'status'),
        Index('ix_matches_scrimmage_quota', 'created_by_team_id', 'created_at'),
    )


class Game(Base):
    __tablename__ = 'games'
    id: Mapped[uuid.UUID] = _id()
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('matches.id', ondelete='CASCADE'), nullable=False)
    game_index: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    blue_submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('submissions.id'), nullable=False)
    red_submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('submissions.id'), nullable=False)
    blue_team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('teams.id'), nullable=False)
    red_team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('teams.id'), nullable=False)
    map_id: Mapped[str] = mapped_column(String(32), nullable=False, default='standard')
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    ruleset_id: Mapped[str] = mapped_column(String(32), nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default='queued')
    winner: Mapped[str | None] = mapped_column(String(4))
    reason: Mapped[str | None] = mapped_column(String(16))
    total_plies: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    replay_key: Mapped[str | None] = mapped_column(Text)
    log_key: Mapped[str | None] = mapped_column(Text)
    error: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _now()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint('match_id', 'game_index', 'attempt'),
        Index('uq_games_current', 'match_id', 'game_index', unique=True, postgresql_where=text('is_current')),
        _enum('status', GAME_STATUSES),
        _enum('winner', SIDES),
        _enum('reason', REASONS),
        CheckConstraint('attempt >= 1', name='attempt_positive'),
        CheckConstraint("(status = 'finished') = (winner IS NOT NULL)", name='finished_has_winner'),
    )


class WorkerJob(Base):
    __tablename__ = 'worker_jobs'
    id: Mapped[uuid.UUID] = _id()  # job_id on the wire and RQ job id
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    queue: Mapped[str] = mapped_column(String(32), nullable=False)
    submission_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('submissions.id'))
    game_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('games.id', ondelete='CASCADE'), unique=True)
    attempt: Mapped[int | None] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default='queued')
    outcome: Mapped[str | None] = mapped_column(String(16))  # ready/failed/finished/infra_error
    lease_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        _enum('kind', ('build', 'match')),
        _enum('queue', QUEUES),
        _enum('status', JOB_STATUSES),
        CheckConstraint("(kind = 'build') = (submission_id IS NOT NULL AND game_id IS NULL)", name='kind_target'),
        Index('ix_worker_jobs_open', 'status', postgresql_where=text("status <> 'terminal'")),
    )


class CallbackReceipt(Base):
    __tablename__ = 'callback_receipts'
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('worker_jobs.id', ondelete='CASCADE'), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    lease_token: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    received_at: Mapped[datetime] = _now()


class Outbox(Base):
    __tablename__ = 'outbox'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)  # job | event
    target: Mapped[str] = mapped_column(Text, nullable=False)  # RQ queue name or WS channel
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('worker_jobs.id', ondelete='CASCADE'))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        _enum('kind', ('job', 'event')),
        Index('ix_outbox_pending', 'id', postgresql_where=text('delivered_at IS NULL')),
    )


class IdempotencyRecord(Base):
    __tablename__ = 'idempotency_records'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict | list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _now()
    __table_args__ = (UniqueConstraint('actor_id', 'method', 'path', 'key'), Index('ix_idempotency_created', 'created_at'))


class RefreshTokenFamily(Base):
    __tablename__ = 'refresh_token_families'
    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    created_at: Mapped[datetime] = _now()
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(32))


class RefreshToken(Base):
    __tablename__ = 'refresh_tokens'
    id: Mapped[uuid.UUID] = _id()
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('refresh_token_families.id', ondelete='CASCADE'), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = _now()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MatchOverride(Base):
    __tablename__ = 'match_overrides'
    id: Mapped[uuid.UUID] = _id()
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('matches.id', ondelete='CASCADE'), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id'))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    before: Mapped[dict] = mapped_column(JSONB, nullable=False)
    after: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _now()


class Standing(Base):
    __tablename__ = 'standings'
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('groups.id', ondelete='CASCADE'), primary_key=True)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('teams.id'), primary_key=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    won: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    drawn: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    game_diff: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    games_won: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    winning_plies: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = _now()


class TiebreakLot(Base):
    """Persisted lot for a tied set so recomputation reuses the audited order."""
    __tablename__ = 'tiebreak_lots'
    id: Mapped[uuid.UUID] = _id()
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('groups.id', ondelete='CASCADE'), nullable=False)
    team_ids_key: Mapped[str] = mapped_column(Text, nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ordered_team_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _now()
    __table_args__ = (UniqueConstraint('group_id', 'team_ids_key'),)


class BracketSlot(Base):
    __tablename__ = 'bracket_slots'
    tournament_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('tournaments.id', ondelete='CASCADE'), primary_key=True)
    round: Mapped[str] = mapped_column(String(16), primary_key=True)
    slot_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_rule: Mapped[str] = mapped_column(String(16), nullable=False)
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('teams.id'))
    match_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('matches.id', ondelete='SET NULL'))
    __table_args__ = (_enum('round', KNOCKOUT_STAGES),)


class Announcement(Base):
    __tablename__ = 'announcements'
    id: Mapped[uuid.UUID] = _id()
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class AuditLog(Base):
    __tablename__ = 'audit_log'
    id: Mapped[uuid.UUID] = _id()
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp())
    __table_args__ = (Index('ix_audit_log_created', text('created_at DESC')),)


class CodeSimilarity(Base):
    __tablename__ = 'code_similarity'
    submission_a: Mapped[uuid.UUID] = mapped_column(ForeignKey('submissions.id'), primary_key=True)
    submission_b: Mapped[uuid.UUID] = mapped_column(ForeignKey('submissions.id'), primary_key=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    checked_at: Mapped[datetime] = _now()
    __table_args__ = (CheckConstraint('submission_a < submission_b', name='ordered_pair'),
                      CheckConstraint('score >= 0 AND score <= 1', name='score_range'))


class WorkerStatus(Base):
    __tablename__ = 'workers'
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (_enum('kind', ('build', 'match')),)


class QueueControl(Base):
    __tablename__ = 'queue_controls'
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = _now()
    __table_args__ = (_enum('name', QUEUES),)
