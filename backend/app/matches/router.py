"""Scrimmages, matches, games and replay URLs."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import idempotency
from app import serializers as ser
from app.config import get_settings
from app.db import get_db
from app.deps import Actor, OpInput, contract_input, require_member, require_team
from app.errors import ApiError, conflict, not_found
from app.matches import admission, service
from app.models import ActiveBot, Game, Match, Submission, Team
from app.queue import commit
from app.storage import get_storage
from app.teams.router import eligible_opponents_query, ensure_team_active
from app.timeutil import iso, saigon_day_bounds, utcnow

router = APIRouter()
SCRIMMAGE_DAILY_LIMIT = 60


def _ready_scrimmage_bot(db: Session, team_id) -> Submission | None:
    return db.scalar(select(Submission).join(ActiveBot, ActiveBot.submission_id == Submission.id)
                     .where(ActiveBot.team_id == team_id, ActiveBot.scope == 'scrimmage',
                            Submission.status == 'ready'))


def _quota(db: Session, team_id) -> dict:
    start, end = saigon_day_bounds(utcnow())
    used = db.scalar(select(func.count()).select_from(Match).where(
        Match.stage == 'scrimmage', Match.created_by_team_id == team_id, Match.created_at >= start,
        Match.created_at < end)) or 0
    return {'limit': SCRIMMAGE_DAILY_LIMIT, 'used': used, 'remaining': max(SCRIMMAGE_DAILY_LIMIT - used, 0),
            'resets_at': iso(end)}


def _quota_body(db: Session, team_id) -> dict:
    return {**_quota(db, team_id), 'active': admission.active_matches(db, team_id),
            'active_limit': get_settings().scrimmage_max_active_per_team, 'admission': admission.admission(db)}


@router.post('/scrimmages', status_code=202)
def create_scrimmage(request: Request, actor: Actor = Depends(require_member),
                     inp: OpInput = Depends(contract_input('createScrimmage')), db: Session = Depends(get_db)):
    idem = idempotency.begin(db, request, actor.id, idempotency.hash_json(inp.body))
    if idem.replay:
        return idem.replay
    team = db.get(Team, require_team(actor), with_for_update=True)  # row lock serializes the quota count
    ensure_team_active(team)
    opponent_id = uuid.UUID(inp.body['opponent_team_id'])
    if opponent_id == team.id:
        raise conflict('SELF_SCRIMMAGE')
    opponent = db.get(Team, opponent_id)
    if opponent is None:
        raise not_found('Không tìm thấy đội đối thủ')
    if db.scalar(eligible_opponents_query().where(Team.id == opponent.id)) is None:
        raise conflict(message='Đội đối thủ hiện không nhận đánh tập', reason='opponent_not_eligible')
    own_bot = _ready_scrimmage_bot(db, team.id)
    if own_bot is None:
        raise conflict('SUBMISSION_NOT_READY', 'Đội chưa có bot đánh tập sẵn sàng')
    if _quota(db, team.id)['remaining'] <= 0:
        raise ApiError(429, 'QUOTA_EXCEEDED', details=_quota(db, team.id))
    admission.ensure_can_create(db, team.id)
    opponent_bot = _ready_scrimmage_bot(db, opponent.id)
    match = Match(stage='scrimmage', team_a_id=team.id, team_b_id=opponent.id, best_of='two_games', status='queued',
                  created_by_team_id=team.id)
    db.add(match)
    db.flush()
    engine_version = get_settings().engine_version
    # Two games with sides swapped, both pinned to the bots active at request time.
    service.create_game(db, match, 1, (team.id, own_bot.id), (opponent.id, opponent_bot.id), engine_version)
    service.create_game(db, match, 2, (opponent.id, opponent_bot.id), (team.id, own_bot.id), engine_version)
    response = idem.record(202, {'match_id': str(match.id), 'status': 'queued'})
    commit(db)
    return response


@router.get('/scrimmages/quota')
def scrimmage_quota(actor: Actor = Depends(require_member), db: Session = Depends(get_db)):
    return _quota_body(db, require_team(actor))


@router.get('/scrimmages')
def list_scrimmages(actor: Actor = Depends(require_member), inp: OpInput = Depends(contract_input('listScrimmages')),
                    db: Session = Depends(get_db)):
    query = select(Match).where(Match.stage == 'scrimmage')
    if not actor.is_admin:
        query = query.where(or_(Match.team_a_id == actor.team_id, Match.team_b_id == actor.team_id))
    query = query.order_by(Match.created_at.desc(), Match.id)
    return ser.page(db, query, inp.params['page'], inp.params['page_size'], lambda rows: ser.matches(db, list(rows)))


@router.get('/matches')
def list_matches(actor: Actor = Depends(require_member), inp: OpInput = Depends(contract_input('listMatches')),
                 db: Session = Depends(get_db)):
    # tournament_id is required by the contract, so this lists tournament matches only (scrimmages: /scrimmages).
    query = select(Match).where(Match.tournament_id == inp.params['tournament_id'])
    if inp.params['status']:
        query = query.where(Match.status == inp.params['status'])
    query = query.order_by(Match.created_at.desc(), Match.id)
    return ser.page(db, query, inp.params['page'], inp.params['page_size'], lambda rows: ser.matches(db, list(rows)))


def visible_match(db: Session, actor: Actor, match_id) -> Match:
    match = db.get(Match, match_id)
    if match is None or not service.can_view(match, actor.team_id, actor.is_admin):
        raise not_found('Không tìm thấy trận')
    return match


def visible_game(db: Session, actor: Actor, game_id) -> Game:
    game = db.get(Game, game_id)
    if game is None:
        raise not_found('Không tìm thấy ván')
    visible_match(db, actor, game.match_id)
    return game


@router.get('/matches/{id}')
def get_match(actor: Actor = Depends(require_member), inp: OpInput = Depends(contract_input('getMatch')),
              db: Session = Depends(get_db)):
    return ser.match(db, visible_match(db, actor, inp.params['id']))


@router.get('/games/{id}')
def get_game(actor: Actor = Depends(require_member), inp: OpInput = Depends(contract_input('getGame')),
             db: Session = Depends(get_db)):
    return ser.game(visible_game(db, actor, inp.params['id']))


@router.get('/games/{id}/replay')
def get_replay_url(actor: Actor = Depends(require_member), inp: OpInput = Depends(contract_input('getReplayUrl')),
                   db: Session = Depends(get_db)):
    game = visible_game(db, actor, inp.params['id'])
    if game.status != 'finished' or not game.replay_key:
        raise conflict(message='Ván chưa có replay', game_status=game.status)
    ttl = get_settings().replay_url_ttl_seconds
    expires = utcnow().timestamp() + ttl
    url = get_storage().presign_get(game.replay_key, ttl)
    return {'url': url, 'expires_at': iso(datetime.fromtimestamp(expires, UTC))}
