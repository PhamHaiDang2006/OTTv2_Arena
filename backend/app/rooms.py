"""Serialized room commands; snapshots survive browser/API restarts."""
import copy
import secrets

from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import idempotency
from app import room_rules as rules
from app.db import get_db
from app.deps import Actor, OpInput, contract_input, require_member
from app.errors import conflict, invalid, not_found
from app.models import PlayRoom, User
from app.profiles import record_result

router = APIRouter()


def snapshot(room):
    state = copy.deepcopy(room.state)
    state.update(id=str(room.id), code=room.code)
    state['legal_moves'] = rules.legal(state['map'], state, state['turn']) if state['status'] == 'playing' else []
    return state


def seat(user_id, side):
    return {'id': str(user_id), 'side': side, 'ready': False, 'rematch': False}


def locked(db, room_id, actor):
    room = db.get(PlayRoom, room_id, with_for_update=True)
    if room is None or actor.id not in (room.host_id, room.guest_id):
        raise not_found('Không tìm thấy phòng của bạn')
    return room


def finish(db, idem, room, status=200):
    db.flush()
    record_result(db, room)
    response = idem.record(status, snapshot(room))
    db.commit()
    return response


@router.post('/rooms', status_code=201)
def create_room(request: Request, actor: Actor = Depends(require_member),
                inp: OpInput = Depends(contract_input('createRoom')), db: Session = Depends(get_db)):
    idem = idempotency.begin(db, request, actor.id, idempotency.hash_json(inp.body))
    if idem.replay:
        return idem.replay
    # Serialize room creation per user to enforce the open-room quota under concurrency.
    db.get(User, actor.id, with_for_update=True)
    active = db.scalars(select(PlayRoom).where(PlayRoom.host_id == actor.id,
                        PlayRoom.state['status'].astext.in_(['waiting', 'playing']))).all()
    if len(active) >= 5:
        raise conflict(message='Bạn đã có 5 phòng đang mở. Hãy rời phòng cũ trước.')
    code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8))
    # Uniqueness is also enforced in PostgreSQL.
    while db.scalar(select(PlayRoom.id).where(PlayRoom.code == code)):
        code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8))
    map_id = inp.body['map']
    room = PlayRoom(code=code, host_id=actor.id, state={
        'map': map_id, 'revision': 0, 'round': 1, 'status': 'waiting',
        'players': [seat(actor.id, 'BLUE')], 'turn': None, 'moves': [], 'result': None, **rules.initial(map_id)})
    db.add(room)
    return finish(db, idem, room, 201)


@router.get('/rooms')
def list_rooms(actor: Actor = Depends(require_member), db: Session = Depends(get_db)):
    rooms = db.scalars(select(PlayRoom).where(or_(PlayRoom.host_id == actor.id, PlayRoom.guest_id == actor.id))
                       .order_by(PlayRoom.created_at.desc(), PlayRoom.id).limit(50)).all()
    return [snapshot(r) for r in rooms]


@router.get('/rooms/{room_id}')
def get_room(actor: Actor = Depends(require_member), inp: OpInput = Depends(contract_input('getRoom')),
             db: Session = Depends(get_db)):
    room = db.get(PlayRoom, inp.params['room_id'])
    if room is None or actor.id not in (room.host_id, room.guest_id):
        raise not_found()
    return snapshot(room)


@router.post('/rooms/join')
def join_room(request: Request, actor: Actor = Depends(require_member),
              inp: OpInput = Depends(contract_input('joinRoom')), db: Session = Depends(get_db)):
    idem = idempotency.begin(db, request, actor.id, idempotency.hash_json(inp.body))
    if idem.replay:
        return idem.replay
    room = db.scalar(select(PlayRoom).where(PlayRoom.code == inp.body['code']).with_for_update())
    if room is None:
        raise not_found('Mã phòng không tồn tại')
    if actor.id not in (room.host_id, room.guest_id):
        if room.guest_id is not None or room.state['status'] != 'waiting':
            raise conflict(message='Phòng đã đủ người hoặc đã đóng')
        room.guest_id = actor.id
        state = copy.deepcopy(room.state)
        state['players'].append(seat(actor.id, 'RED'))
        state['revision'] += 1
        room.state = state
    return finish(db, idem, room)


@router.post('/rooms/{room_id}/commands')
def command(request: Request, actor: Actor = Depends(require_member),
            inp: OpInput = Depends(contract_input('roomCommand')), db: Session = Depends(get_db)):
    idem = idempotency.begin(db, request, actor.id, idempotency.hash_json(inp.body))
    if idem.replay:
        return idem.replay
    room = locked(db, inp.params['room_id'], actor)
    state = copy.deepcopy(room.state)
    if state['revision'] != inp.body['revision']:
        raise conflict(message='Phòng vừa thay đổi. Đã tải lại trạng thái, hãy thử lại.')
    action = inp.body['action']
    player = next(p for p in state['players'] if p['id'] == str(actor.id))
    status = state['status']
    if action in ('ready', 'unready') and status == 'waiting':
        player['ready'] = action == 'ready'
        if len(state['players']) == 2 and all(p['ready'] for p in state['players']):
            state.update(status='playing', turn='BLUE')
    elif action == 'move' and status == 'playing' and state['turn'] == player['side']:
        move = inp.body.get('move')
        if move is None:
            raise invalid('Thiếu nước đi')
        try:
            state['result'] = rules.apply(state['map'], state, player['side'], move, len(state['moves'])+1)
        except ValueError as exc:
            raise invalid(str(exc)) from exc
        state['moves'].append(move)
        state['turn'] = rules.other(player['side'])
        if state['result']:
            state.update(status='finished', turn=None)
    elif action == 'resign' and status == 'playing':
        state.update(status='finished', turn=None, result={'winner': rules.other(player['side']), 'reason': 'RESIGNED'})
    elif action == 'rematch' and status == 'finished':
        player['rematch'] = True
        if all(p['rematch'] for p in state['players']):
            for p in state['players']:
                p.update(side=rules.other(p['side']), ready=True, rematch=False)
            state.update(status='playing', turn='BLUE', moves=[], result=None, round=state['round']+1,
                         **rules.initial(state['map']))
    elif action == 'leave' and status != 'closed':
        if status == 'playing':
            state['result'] = {'winner': rules.other(player['side']), 'reason': 'RESIGNED'}
        state.update(status='closed', turn=None)
    else:
        raise conflict(message='Chưa đến lượt hoặc thao tác không phù hợp với trạng thái phòng')
    state['revision'] += 1
    room.state = state
    return finish(db, idem, room)
