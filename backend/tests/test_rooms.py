"""Room lifecycle, durable recovery, authority and optimistic concurrency."""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import room_rules as rules
from app.main import app
from tests.helpers import bearer, make_user, token_for


def callers():
    return [bearer(token_for(make_user(f'room-{i}@example.test'))) for i in range(3)]


@pytest.mark.parametrize('vector', json.loads((Path(__file__).resolve().parents[2] /
                          'contracts/fixtures/room-games.json').read_text(encoding='utf-8')))
def test_special_rules_shared_vectors(vector):
    state = rules.initial(vector['map'])
    assert state['position'] == vector['initial']
    result = None
    for i, move in enumerate(vector['moves']):
        assert result is None
        result = rules.apply(vector['map'], state, 'RED' if i % 2 else 'BLUE', move, i+1)
    assert state['position'] == vector['position']
    assert result == vector['result']


@pytest.mark.parametrize('map_id', ['standard', 'hexagon', 'circular'])
def test_room_lifecycle_and_recovery(api, map_id):
    host, guest, stranger = callers()
    created = api.post('/api/v1/rooms', json={'map': map_id}, headers=host)
    assert created.status_code == 201
    room = created.json()
    url = f'/api/v1/rooms/{room["id"]}'
    assert api.get(url, headers=stranger).status_code == 404
    assert api.get(url).status_code == 401
    assert api.post(url+'/commands', headers=stranger, json={'revision': 0, 'action': 'ready'}).status_code == 404
    joined = api.post('/api/v1/rooms/join', headers=guest, json={'code': room['code']}).json()
    assert len(joined['players']) == 2
    assert api.post('/api/v1/rooms/join', headers=stranger, json={'code': room['code']}).status_code == 409
    assert api.post('/api/v1/rooms/join', headers=host, json={'code': room['code']}).json()['revision'] == 1

    def command(who, action, **extra):
        current = api.get(url, headers=who).json()
        return api.post(url+'/commands', headers=who, json={'revision': current['revision'], 'action': action, **extra})

    assert command(host, 'ready').json()['status'] == 'waiting'
    playing = command(guest, 'ready').json()
    assert playing['status'] == 'playing'
    assert command(guest, 'move', move=playing['legal_moves'][0]).status_code == 409
    assert command(host, 'move', move={'from': 'xx', 'to': 'yy'}).status_code == 422
    body = {'revision': playing['revision'], 'action': 'move', 'move': playing['legal_moves'][0]}
    key = str(uuid.uuid4())
    moved = api.post(url+'/commands', headers=host, json=body, idem=key)
    assert len(moved.json()['moves']) == 1
    assert api.post(url+'/commands', headers=host, json=body, idem=key).json() == moved.json()
    assert api.post(url+'/commands', headers=host, json=body).status_code == 409
    with TestClient(app) as fresh:
        assert fresh.get(url, headers=guest).json() == moved.json()
    ended = command(guest, 'resign').json()
    assert ended['result'] == {'winner': 'BLUE', 'reason': 'RESIGNED'}
    assert command(host, 'rematch').json()['status'] == 'finished'
    replay = command(guest, 'rematch').json()
    assert replay['round'] == 2 and replay['moves'] == [] and replay['status'] == 'playing'
    assert replay['players'][0]['side'] == 'RED'
    assert command(host, 'move', move=replay['legal_moves'][0]).status_code == 409
    assert command(guest, 'leave').json()['status'] == 'closed'
    assert command(host, 'rematch').status_code == 409
    assert api.get('/api/v1/rooms', headers=host).json()[0]['id'] == room['id']


def test_concurrent_join_claims_only_one_seat(api):
    host, a, b = callers()
    room = api.post('/api/v1/rooms', headers=host, json={'map': 'hexagon'}).json()

    def join(headers):
        with TestClient(app) as client:
            return client.post('/api/v1/rooms/join', headers={**headers, 'Idempotency-Key': str(uuid.uuid4())},
                               json={'code': room['code']}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(join, [a, b])) == [200, 409]
    assert len(api.get(f'/api/v1/rooms/{room["id"]}', headers=host).json()['players']) == 2


def test_create_retry_does_not_duplicate_and_quota(api):
    host = bearer(token_for(make_user('host@example.test')))
    key = str(uuid.uuid4())
    first = api.post('/api/v1/rooms', headers=host, json={'map': 'standard'}, idem=key)
    assert api.post('/api/v1/rooms', headers=host, json={'map': 'standard'}, idem=key).json() == first.json()
    assert api.post('/api/v1/rooms', headers=host, json={'map': 'hexagon'}, idem=key).status_code == 409
    for _ in range(4):
        assert api.post('/api/v1/rooms', headers=host, json={'map': 'standard'}).status_code == 201
    assert api.post('/api/v1/rooms', headers=host, json={'map': 'standard'}).status_code == 409
