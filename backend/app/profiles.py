"""Public profile DTOs never contain login email, role, or team membership."""
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import case, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import idempotency
from app.db import get_db
from app.deps import Actor, OpInput, contract_input, require_member
from app.errors import invalid, not_found
from app.models import PlayerProfile, RoomResult, User

router = APIRouter()
FIELDS = ('display_name', 'bio', 'avatar', 'frame', 'color')


def record_result(db, room):
    state = room.state
    if state['status'] not in ('finished', 'closed') or not state['result'] or len(state['players']) != 2:
        return
    players = {p['side']: uuid.UUID(p['id']) for p in state['players']}
    db.execute(insert(RoomResult).values(room_id=room.id, round=state['round'], map=state['map'],
                                        blue_id=players['BLUE'], red_id=players['RED'],
                                        winner_id=players[state['result']['winner']])
               .on_conflict_do_nothing(index_elements=['room_id', 'round']))


def profile(db, user_id):
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise not_found('Không tìm thấy người chơi')
    row = db.get(PlayerProfile, user_id)
    data = {k: getattr(row, k) for k in FIELDS} if row else {
        'display_name': f'Người chơi {str(user_id)[:8]}', 'bio': '', 'avatar': 'hammer', 'frame': 'none', 'color': 'amber'}
    rows = db.execute(select(RoomResult.map, func.count(),
                      func.sum(case((RoomResult.winner_id == user_id, 1), else_=0)))
                      .where(or_(RoomResult.blue_id == user_id, RoomResult.red_id == user_id))
                      .group_by(RoomResult.map)).all()
    counts = {m: (int(played), int(wins)) for m, played, wins in rows}
    by_map = []
    for m in ('standard', 'hexagon', 'circular'):
        played, wins = counts.get(m, (0, 0))
        by_map.append({'map': m, 'played': played, 'wins': wins, 'losses': played-wins})
    stats = {key: sum(m[key] for m in by_map) for key in ('played', 'wins', 'losses')}
    return {'user_id': str(user_id), **data, 'stats': {**stats, 'by_map': by_map}}


@router.get('/profiles/me')
def my_profile(actor: Actor = Depends(require_member), db: Session = Depends(get_db)):
    return profile(db, actor.id)


@router.put('/profiles/me')
def update_profile(request: Request, actor: Actor = Depends(require_member),
                   inp: OpInput = Depends(contract_input('updateMyProfile')), db: Session = Depends(get_db)):
    idem = idempotency.begin(db, request, actor.id, idempotency.hash_json(inp.body))
    if idem.replay:
        return idem.replay
    values = dict(inp.body)
    values['display_name'] = values['display_name'].strip()
    values['bio'] = values['bio'].strip()
    if not values['display_name'] or any(ord(c) < 32 for c in values['display_name']):
        raise invalid('Tên hiển thị không được trống hoặc chứa ký tự điều khiển')
    db.get(User, actor.id, with_for_update=True)
    row = db.get(PlayerProfile, actor.id)
    if row is None:
        db.add(PlayerProfile(user_id=actor.id, **values))
    else:
        for key, value in values.items():
            setattr(row, key, value)
    db.flush()
    response = idem.record(200, profile(db, actor.id))
    db.commit()
    return response


@router.get('/profiles/{user_id}')
def public_profile(inp: OpInput = Depends(contract_input('publicProfile')), db: Session = Depends(get_db)):
    return profile(db, inp.params['user_id'])
