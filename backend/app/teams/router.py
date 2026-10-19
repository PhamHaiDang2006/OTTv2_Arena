"""Participant team endpoints. The acting team always comes from the authenticated membership."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app import idempotency
from app import serializers as ser
from app.db import get_db
from app.deps import Actor, OpInput, contract_input, require_captain, require_member
from app.errors import ApiError, conflict, invalid, not_found
from app.models import ActiveBot, Submission, Team
from app.queue import commit
from app.timeutil import utcnow

router = APIRouter()


def own_team(db: Session, actor: Actor, lock: bool = False) -> Team:
    if actor.team_id is None:
        raise not_found('Tài khoản không thuộc đội nào')
    team = db.get(Team, actor.team_id, with_for_update=lock)
    if team is None:
        raise not_found()
    return team


def ensure_team_active(team: Team) -> None:
    if team.status == 'disqualified' or team.is_locked:
        raise conflict(message='Đội đang bị khóa hoặc đã bị loại', team_status=team.status, is_locked=team.is_locked)


@router.get('/teams/me')
def my_team(actor: Actor = Depends(require_member), db: Session = Depends(get_db)):
    return ser.team(db, own_team(db, actor))


@router.patch('/teams/me')
def update_my_team(request: Request, actor: Actor = Depends(require_captain),
                   inp: OpInput = Depends(contract_input('updateMyTeam')), db: Session = Depends(get_db)):
    idem = idempotency.begin(db, request, actor.id, idempotency.hash_json(inp.body))
    if idem.replay:
        return idem.replay
    name = inp.body['name'].strip()
    if not name:
        raise invalid('Tên đội không được để trống', field='name')
    team = own_team(db, actor, lock=True)
    team.name = name
    body = ser.team(db, team)
    response = idem.record(200, body)
    commit(db)
    return response


@router.put('/teams/me/active-bot')
def set_active_bot(request: Request, actor: Actor = Depends(require_captain),
                   inp: OpInput = Depends(contract_input('setActiveBot')), db: Session = Depends(get_db)):
    idem = idempotency.begin(db, request, actor.id, idempotency.hash_json(inp.body))
    if idem.replay:
        return idem.replay
    team = own_team(db, actor, lock=True)
    ensure_team_active(team)
    submission = db.get(Submission, uuid.UUID(inp.body['submission_id']))
    if submission is None or submission.team_id != team.id:
        raise not_found('Không tìm thấy bản nộp của đội')
    if submission.status != 'ready':
        raise conflict('SUBMISSION_NOT_READY', submission_status=submission.status)
    scope = inp.body['scope']
    bot = db.get(ActiveBot, (team.id, scope))
    if bot is None:
        bot = ActiveBot(team_id=team.id, scope=scope, submission_id=submission.id)
        db.add(bot)
    else:
        bot.submission_id, bot.updated_at = submission.id, utcnow()
    db.flush()
    response = idem.record(200, ser.active_bot(bot))
    commit(db)
    return response


def eligible_opponents_query():
    """Approved, unlocked teams with a ready scrimmage bot (contracts/behavior.md)."""
    ready_bot = exists().where(ActiveBot.team_id == Team.id, ActiveBot.scope == 'scrimmage',
                               ActiveBot.submission_id == Submission.id, Submission.status == 'ready')
    return select(Team).where(Team.status == 'approved', Team.is_locked.is_(False), ready_bot)


@router.get('/teams/opponents')
def list_opponents(actor: Actor = Depends(require_member), inp: OpInput = Depends(contract_input('listOpponents')),
                   db: Session = Depends(get_db)):
    query = eligible_opponents_query()
    if actor.team_id is not None:
        query = query.where(Team.id != actor.team_id)
    query = query.order_by(Team.created_at.desc(), Team.id)
    return ser.page(db, query, inp.params['page'], inp.params['page_size'],
                    lambda rows: [ser.team_public(t) for t in rows])


def require_actor_team(actor: Actor) -> None:
    if actor.team_id is None:
        raise ApiError(403, 'FORBIDDEN', 'Tài khoản không thuộc đội nào')
