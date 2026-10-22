"""Trusted built-in bots only. Rules come from the engine's public API; no participant code runs here."""
import copy
import random
import uuid

from fastapi import APIRouter, Depends, Request
from ottv2 import INITIAL_FEN, Board, outcome
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import idempotency, ratelimit, serializers
from app.db import get_db
from app.deps import Actor, OpInput, contract_input, require_member
from app.errors import conflict, invalid, not_found
from app.models import CasualGame
from app.timeutil import iso, utcnow

router = APIRouter()


def opposite(side):
    return 'RED' if side == 'BLUE' else 'BLUE'


def advance(state, move):
    board = Board.from_fen(state['fen'])
    mover = state['turn']
    if not board.is_legal(move, mover):
        raise invalid('Nước đi không hợp lệ', field='move')
    capture = board.push(move, mover)[3]
    state['moves'].append({'side': mover, 'move': move, 'capture': capture})
    state['ply'] += 1
    state['fen'] = board.fen()
    result = outcome(board, mover, state['ply'], 300)
    if result:
        state['status'] = 'finished'
        state['winner'], state['reason'] = result
        state['turn'], state['legal_moves'] = None, []
    else:
        state['turn'] = opposite(mover)
        state['legal_moves'] = board.legal_moves(state['turn'])


def bot_turn(state):
    if state['status'] != 'playing' or state['turn'] == state['human_side']:
        return
    rng = random.Random(f"{state['id']}:{state['ply']}")
    moves = list(state['legal_moves'])
    rng.shuffle(moves)
    if state['bot'] == 'greedy':
        board = Board.from_fen(state['fen'])

        def score(move):
            target = (int(move[3]) - 1) * 9 + ord(move[2]) - ord('a')
            result = outcome(board.apply(move, state['turn']), state['turn'], state['ply'] + 1, 300)
            goal = 80 if state['turn'] == 'BLUE' else 0
            distance = max(abs(target % 9 - goal % 9), abs(target // 9 - goal // 9))
            return bool(result and result[0] == state['turn']), bool(board.cells[target]), -distance

        move = max(moves, key=score)
    else:
        move = moves[0]
    advance(state, move)


def owned(db, actor, game_id, lock=False):
    query = select(CasualGame).where(CasualGame.id == game_id, CasualGame.user_id == actor.id)
    if lock:
        query = query.with_for_update()
    game = db.scalar(query)
    if game is None:
        raise not_found('Không tìm thấy ván Casual của bạn')
    return game


@router.post('/casual/games', status_code=201)
def create_game(request: Request, actor: Actor = Depends(require_member),
                inp: OpInput = Depends(contract_input('createCasualGame')), db: Session = Depends(get_db)):
    idem = idempotency.begin(db, request, actor.id, idempotency.hash_json(inp.body))
    if idem.replay:
        return idem.replay
    ratelimit.hit('casual-create', str(actor.id), 30, 3600)
    game_id = uuid.uuid4()
    state = dict(id=str(game_id), fen=INITIAL_FEN, human_side=inp.body['human_side'], bot=inp.body['bot'],
                 status='playing', ply=0, turn='BLUE', legal_moves=Board.from_fen(INITIAL_FEN).legal_moves('BLUE'),
                 moves=[], winner=None, reason=None, created_at=iso(utcnow()))
    bot_turn(state)
    db.add(CasualGame(id=game_id, user_id=actor.id, state=state))
    response = idem.record(201, state)
    db.commit()
    return response


@router.get('/casual/games')
def list_games(actor: Actor = Depends(require_member), inp: OpInput = Depends(contract_input('listCasualGames')),
               db: Session = Depends(get_db)):
    query = select(CasualGame).where(CasualGame.user_id == actor.id).order_by(CasualGame.created_at.desc(), CasualGame.id)
    return serializers.page(db, query, inp.params['page'], inp.params['page_size'], lambda rows: [g.state for g in rows])


@router.get('/casual/games/{id}')
def get_game(actor: Actor = Depends(require_member), inp: OpInput = Depends(contract_input('getCasualGame')),
             db: Session = Depends(get_db)):
    return owned(db, actor, inp.params['id']).state


def mutate(request, actor, inp, db, resign=False):
    idem = idempotency.begin(db, request, actor.id, idempotency.hash_json(inp.body))
    if idem.replay:
        return idem.replay
    game = owned(db, actor, inp.params['id'], lock=True)
    state = copy.deepcopy(game.state)
    if state['status'] != 'playing' or state['ply'] != inp.body['expected_ply']:
        raise conflict(message='Ván đã thay đổi. Hãy tải lại bàn cờ.', current_ply=state['ply'])
    if resign:
        state.update(status='finished', winner=opposite(state['human_side']), reason='RESIGNED', turn=None, legal_moves=[])
    else:
        if state['turn'] != state['human_side']:
            raise conflict(message='Chưa đến lượt của bạn')
        advance(state, inp.body['move'])
        bot_turn(state)
    game.state = state
    response = idem.record(200, state)
    db.commit()
    return response


@router.post('/casual/games/{id}/moves')
def move(request: Request, actor: Actor = Depends(require_member),
         inp: OpInput = Depends(contract_input('moveCasualGame')), db: Session = Depends(get_db)):
    return mutate(request, actor, inp, db)


@router.post('/casual/games/{id}/resign')
def resign(request: Request, actor: Actor = Depends(require_member),
           inp: OpInput = Depends(contract_input('resignCasualGame')), db: Session = Depends(get_db)):
    return mutate(request, actor, inp, db, resign=True)
