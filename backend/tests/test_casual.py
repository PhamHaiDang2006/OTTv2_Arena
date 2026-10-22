"""Casual API uses the real engine, isolated from tournament and worker state."""
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from ottv2 import INITIAL_FEN, Board, outcome
from sqlalchemy import func, select

from app.db import session_scope
from app.models import CasualGame, Match, WorkerJob
from tests.helpers import bearer, make_user, token_for

BASE = '/api/v1/casual/games'


@pytest.fixture
def player():
    return bearer(token_for(make_user('casual@example.test', password=None)))


def create(api, player, side='BLUE', bot='random', **kwargs):
    response = api.post(BASE, headers=player, json={'human_side': side, 'bot': bot}, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize('side', ['BLUE', 'RED'])
@pytest.mark.parametrize('bot', ['random', 'greedy'])
def test_create_move_persist_and_engine_agree(api, player, side, bot):
    game = create(api, player, side, bot)
    assert game['ply'] == (0 if side == 'BLUE' else 1)
    response = api.post(f"{BASE}/{game['id']}/moves", headers=player,
                        json={'move': game['legal_moves'][0], 'expected_ply': game['ply']})
    assert response.status_code == 200
    state = response.json()
    assert state['ply'] == game['ply'] + 2
    board = Board.from_fen(INITIAL_FEN)
    for item in state['moves']:
        assert board.is_legal(item['move'], item['side'])
        assert board.push(item['move'], item['side'])[3] == item['capture']
    assert board.fen() == state['fen']
    assert state['legal_moves'] == board.legal_moves(side)
    assert api.get(f"{BASE}/{game['id']}", headers=player).json() == state
    assert api.get(BASE, headers=player).json()['items'] == [state]
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(Match)) == 0
        assert db.scalar(select(func.count()).select_from(WorkerJob)) == 0


def test_idempotency_and_stale_tabs(api, player):
    key = str(uuid.uuid4())
    game = create(api, player, idem=key)
    assert create(api, player, idem=key) == game
    assert api.get(BASE, headers=player).json()['total'] == 1
    path = f"{BASE}/{game['id']}/moves"
    body = {'move': game['legal_moves'][0], 'expected_ply': 0}
    key = str(uuid.uuid4())
    first = api.post(path, headers=player, json=body, idem=key)
    assert first.status_code == 200
    assert api.post(path, headers=player, json=body, idem=key).json() == first.json()
    assert api.post(path, headers=player, json=body).status_code == 409
    assert api.get(f"{BASE}/{game['id']}", headers=player).json() == first.json()


def test_invalid_move_and_server_owned_state(api, player):
    game = create(api, player)
    for body in ({'move': 'a1i9', 'expected_ply': 0},
                 {'move': game['legal_moves'][0], 'expected_ply': 0, 'winner': 'BLUE'}):
        assert api.post(f"{BASE}/{game['id']}/moves", headers=player, json=body).status_code == 422
    assert api.get(f"{BASE}/{game['id']}", headers=player).json() == game


def test_owner_only_and_resign(api, player):
    game = create(api, player)
    other = bearer(token_for(make_user('other@example.test', 'admin', password=None)))
    path = f"{BASE}/{game['id']}"
    assert api.get(BASE).status_code == 401
    assert api.get(BASE, headers=other).json()['total'] == 0
    assert api.get(path, headers=other).status_code == 404
    assert api.post(path + '/resign', headers=other, json={'expected_ply': 0}).status_code == 404
    result = api.post(path + '/resign', headers=player, json={'expected_ply': 0})
    assert result.status_code == 200
    assert (result.json()['winner'], result.json()['reason'], result.json()['legal_moves']) == ('RED', 'RESIGNED', [])
    assert api.post(path + '/moves', headers=player,
                    json={'move': game['legal_moves'][0], 'expected_ply': 0}).status_code == 409


def test_goal_ends_before_bot_reply(api, player):
    game = create(api, player)
    cells = [None] * 81
    cells[70], cells[10] = 'B', 'k'  # h8 -> i9 wins immediately
    board = Board(cells)
    with session_scope() as db:
        row = db.get(CasualGame, uuid.UUID(game['id']))
        row.state = {**row.state, 'fen': board.fen(), 'legal_moves': board.legal_moves('BLUE')}
    response = api.post(f"{BASE}/{game['id']}/moves", headers=player,
                        json={'move': 'h8i9', 'expected_ply': 0})
    result = response.json()
    assert response.status_code == 200
    assert (result['winner'], result['reason'], result['ply']) == ('BLUE', 'GOAL', 1)
    assert result['turn'] is None and result['legal_moves'] == []
    assert outcome(Board.from_fen(result['fen']), 'BLUE', 1) == ('BLUE', 'GOAL')


def test_concurrent_moves_accept_only_one_turn(api, player):
    game = create(api, player)

    def send():
        return api.post(f"{BASE}/{game['id']}/moves", headers=player,
                        json={'move': game['legal_moves'][0], 'expected_ply': 0}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: send(), range(2)))
    assert sorted(results) == [200, 409]
    assert api.get(f"{BASE}/{game['id']}", headers=player).json()['ply'] == 2


@pytest.mark.parametrize('bot', ['random', 'greedy'])
def test_complete_game_uses_engine_terminal_rules(api, player, bot):
    from app.casual import advance, bot_turn
    state = create(api, player, bot=bot)
    while state['status'] == 'playing':
        advance(state, state['legal_moves'][0])
        bot_turn(state)
        assert state['ply'] <= 300
    last = state['moves'][-1]
    assert outcome(Board.from_fen(state['fen']), last['side'], state['ply']) == (state['winner'], state['reason'])
    assert state['legal_moves'] == [] and state['turn'] is None
