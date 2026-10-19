"""ORM rows → wire dicts. Field names come from contracts/schemas/common.schema.json; tests validate every
response against it. Sensitive columns (source keys, image tags, password hashes, seeds) are never exposed."""
from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.models import (
    ActiveBot,
    Announcement,
    AuditLog,
    BracketSlot,
    CodeSimilarity,
    Game,
    Group,
    GroupTeam,
    Match,
    Round,
    RoundSnapshot,
    Standing,
    Submission,
    Team,
    TeamMember,
    Tournament,
    User,
    WorkerStatus,
)
from app.timeutil import iso, utcnow


def s(value: uuid.UUID | None) -> str | None:
    return None if value is None else str(value)


def user(row: User, team_id: uuid.UUID | None) -> dict[str, Any]:
    return {'id': s(row.id), 'email': row.email, 'role': row.role, 'team_id': s(team_id), 'is_active': row.is_active}


def team_public(row: Team) -> dict[str, Any]:
    return {'id': s(row.id), 'name': row.name, 'slug': row.slug}


def current_group_id(db: Session, team_id: uuid.UUID) -> uuid.UUID | None:
    """Group of the team in the most recently created tournament that has a draw."""
    return db.scalar(
        select(GroupTeam.group_id).join(Group, Group.id == GroupTeam.group_id)
        .join(Tournament, Tournament.id == Group.tournament_id)
        .where(GroupTeam.team_id == team_id).order_by(Tournament.created_at.desc()).limit(1))


def team(db: Session, row: Team) -> dict[str, Any]:
    members = db.scalars(select(User).join(TeamMember, TeamMember.user_id == User.id)
                         .where(TeamMember.team_id == row.id).order_by(User.created_at, User.id))
    bots = db.scalars(select(ActiveBot).where(ActiveBot.team_id == row.id).order_by(ActiveBot.scope))
    return {**team_public(row), 'status': row.status, 'is_locked': row.is_locked, 'seed': row.seed,
            'group_id': s(current_group_id(db, row.id)),
            'members': [user(m, row.id) for m in members],
            'active_bots': [active_bot(b) for b in bots]}


def active_bot(row: ActiveBot) -> dict[str, Any]:
    return {'team_id': s(row.team_id), 'scope': row.scope, 'submission_id': s(row.submission_id)}


def submission(row: Submission) -> dict[str, Any]:
    error = None
    if row.build_error:
        error = {'code': row.build_error['code'], 'message': row.build_error['message']}
    return {'id': s(row.id), 'team_id': s(row.team_id), 'language': row.language, 'status': row.status,
            'sha256': row.sha256, 'submitted_at': iso(row.submitted_at), 'build_error': error}


def game(row: Game) -> dict[str, Any]:
    finished = row.status == 'finished'
    duration = row.duration_ms
    if row.status == 'running' and duration is None:
        duration = 0
    return {'id': s(row.id), 'match_id': s(row.match_id), 'game_index': row.game_index, 'attempt': row.attempt,
            'is_current': row.is_current, 'blue_submission_id': s(row.blue_submission_id),
            'red_submission_id': s(row.red_submission_id), 'map_id': row.map_id, 'engine_version': row.engine_version,
            'ruleset_id': row.ruleset_id, 'status': row.status,
            'result': {'winner': row.winner, 'reason': row.reason, 'plies': row.total_plies} if finished else None,
            'duration_ms': duration if row.status != 'queued' else None,
            'replay_available': finished}


def matches(db: Session, rows: list[Match]) -> list[dict[str, Any]]:
    if not rows:
        return []
    ids = [m.id for m in rows]
    games_by_match: dict[uuid.UUID, list[Game]] = defaultdict(list)
    for g in db.scalars(select(Game).where(Game.match_id.in_(ids)).order_by(Game.game_index, Game.attempt)):
        games_by_match[g.match_id].append(g)
    team_ids = {m.team_a_id for m in rows} | {m.team_b_id for m in rows}
    teams = {t.id: t for t in db.scalars(select(Team).where(Team.id.in_(team_ids)))}
    return [{'id': s(m.id), 'tournament_id': s(m.tournament_id), 'round_id': s(m.round_id), 'stage': m.stage,
             'team_a': team_public(teams[m.team_a_id]), 'team_b': team_public(teams[m.team_b_id]),
             'best_of': m.best_of, 'status': m.status, 'winner_team_id': s(m.winner_team_id),
             'score_a': m.score_a, 'score_b': m.score_b, 'games': [game(g) for g in games_by_match[m.id]]}
            for m in rows]


def match(db: Session, row: Match) -> dict[str, Any]:
    return matches(db, [row])[0]


def announcement(row: Announcement) -> dict[str, Any]:
    return {'id': s(row.id), 'title': row.title, 'body': row.body, 'published_at': iso(row.published_at)}


def tournament(row: Tournament) -> dict[str, Any]:
    return {'id': s(row.id), 'name': row.name, 'status': row.status, 'engine_version': row.engine_version,
            'ruleset_id': row.ruleset_id, 'draw_seed': row.draw_seed, 'draw_locked': row.draw_locked}


def round_(db: Session, row: Round) -> dict[str, Any]:
    snapshot_id = db.scalar(select(RoundSnapshot.id).where(RoundSnapshot.round_id == row.id))
    total = db.scalar(select(func.count()).select_from(Match).where(Match.round_id == row.id)) or 0
    done = db.scalar(select(func.count()).select_from(Match)
                     .where(Match.round_id == row.id, Match.status == 'finished')) or 0
    return {'id': s(row.id), 'tournament_id': s(row.tournament_id), 'stage': row.stage, 'status': row.status,
            'freeze_at': iso(row.freeze_at), 'snapshot_id': s(snapshot_id), 'matches_total': total,
            'matches_finished': done}


def standing(row: Standing, team_row: Team) -> dict[str, Any]:
    return {'group_id': s(row.group_id), 'team': team_public(team_row), 'rank': row.rank, 'played': row.played,
            'won': row.won, 'drawn': row.drawn, 'lost': row.lost, 'points': row.points, 'game_diff': row.game_diff,
            'games_won': row.games_won, 'winning_plies': row.winning_plies}


def bracket_slot(row: BracketSlot, team_row: Team | None) -> dict[str, Any]:
    return {'round': row.round, 'slot_index': row.slot_index, 'source_rule': row.source_rule,
            'team': team_public(team_row) if team_row else None, 'match_id': s(row.match_id)}


def audit(row: AuditLog) -> dict[str, Any]:
    return {'id': s(row.id), 'actor_user_id': s(row.actor_user_id), 'action': row.action,
            'target_type': row.target_type, 'target_id': s(row.target_id), 'payload': row.payload,
            'created_at': iso(row.created_at)}


def similarity(row: CodeSimilarity) -> dict[str, Any]:
    return {'submission_a': s(row.submission_a), 'submission_b': s(row.submission_b), 'score': row.score,
            'checked_at': iso(row.checked_at)}


WORKER_OFFLINE_SECONDS = 90


def worker(row: WorkerStatus) -> dict[str, Any]:
    age = (utcnow() - row.last_seen_at).total_seconds()
    status = 'offline' if age > WORKER_OFFLINE_SECONDS else 'busy' if row.job_id else 'idle'
    return {'id': row.id, 'kind': row.kind, 'last_seen_at': iso(row.last_seen_at), 'status': status,
            'job_id': s(row.job_id)}


def page(db: Session, query: Select, page_number: int, page_size: int,
         render: Callable[[Iterable[Any]], list[dict[str, Any]]]) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = list(db.scalars(query.limit(page_size).offset((page_number - 1) * page_size)))
    return {'items': render(rows), 'page': page_number, 'page_size': page_size, 'total': total}
