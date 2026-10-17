from __future__ import annotations

import time

import jwt
import pytest
from starlette.websockets import WebSocketDisconnect

from app import contract
from app.queue import publish_event
from tests.conftest import ORIGIN
from tests.helpers import make_admin, make_team

HEADERS = {'origin': ORIGIN}


def receive(ws):
    message = ws.receive_json()
    assert not contract.errors('WsServer', message), message
    return message


def test_origin_is_checked_at_handshake(raw_client):
    with pytest.raises(WebSocketDisconnect):
        with raw_client.websocket_connect('/ws', headers={'origin': 'https://evil.example'}):
            pass
    with pytest.raises(WebSocketDisconnect):
        with raw_client.websocket_connect('/ws'):
            pass


def test_ping_public_subscribe_and_invalid_messages(raw_client):
    with raw_client.websocket_connect('/ws', headers=HEADERS) as ws:
        ws.send_json({'type': 'ping'})
        assert receive(ws) == {'type': 'pong'}
        ws.send_json({'type': 'subscribe', 'channel': 'public'})
        assert receive(ws) == {'type': 'subscribed', 'channel': 'public'}
        ws.send_json({'type': 'subscribe', 'channel': 'public'})  # duplicate: acked, not double-registered
        assert receive(ws) == {'type': 'subscribed', 'channel': 'public'}
        ws.send_text('not json')
        assert receive(ws)['code'] == 'INVALID_MESSAGE'
        ws.send_json({'type': 'subscribe', 'channel': 'team:abc'})
        assert receive(ws)['code'] == 'INVALID_MESSAGE'
        ws.send_text('x' * (16 * 1024 + 1))
        assert receive(ws)['code'] == 'INVALID_MESSAGE'
        ws.send_json({'type': 'unsubscribe', 'channel': 'public'})
        assert receive(ws) == {'type': 'unsubscribed', 'channel': 'public'}


def test_team_channel_requires_auth_and_membership(raw_client):
    a, b = make_team('doi-a'), make_team('doi-b')
    token = a.member['Authorization'].split()[1]
    with raw_client.websocket_connect('/ws', headers=HEADERS) as ws:
        ws.send_json({'type': 'subscribe', 'channel': f'team:{a.id}'})
        assert receive(ws)['code'] == 'UNAUTHORIZED'
        ws.send_json({'type': 'auth', 'access_token': token})
        assert receive(ws) == {'type': 'auth.ok'}
        ws.send_json({'type': 'subscribe', 'channel': f'team:{b.id}'})
        assert receive(ws)['code'] == 'FORBIDDEN'
        ws.send_json({'type': 'subscribe', 'channel': f'team:{a.id}'})
        assert receive(ws) == {'type': 'subscribed', 'channel': f'team:{a.id}'}
        ws.send_json({'type': 'auth', 'access_token': 'garbage'})
        assert receive(ws)['code'] == 'UNAUTHORIZED'


def test_events_fan_out_only_to_subscribed_channels(raw_client):
    a, b = make_team('doi-a'), make_team('doi-b')
    with raw_client.websocket_connect('/ws', headers=HEADERS) as ws_a, \
            raw_client.websocket_connect('/ws', headers=HEADERS) as ws_public:
        ws_a.send_json({'type': 'auth', 'access_token': a.member['Authorization'].split()[1]})
        receive(ws_a)
        ws_a.send_json({'type': 'subscribe', 'channel': f'team:{a.id}'})
        receive(ws_a)
        ws_public.send_json({'type': 'subscribe', 'channel': 'public'})
        receive(ws_public)
        time.sleep(0.3)  # hub subscribed to Redis in the app lifespan
        private = {'schema_version': 1, 'event_id': '00000000-0000-4000-8000-000000000001', 'type': 'build.updated',
                   'channel': f'team:{b.id}', 'occurred_at': '2026-10-17T00:00:00Z',
                   'data': {'submission_id': '00000000-0000-4000-8000-000000000002', 'status': 'ready'}}
        mine = {**private, 'event_id': '00000000-0000-4000-8000-000000000003', 'channel': f'team:{a.id}'}
        public = {'schema_version': 1, 'event_id': '00000000-0000-4000-8000-000000000004',
                  'type': 'announcement.published', 'channel': 'public', 'occurred_at': '2026-10-17T00:00:00Z',
                  'data': {'announcement_id': '00000000-0000-4000-8000-000000000005'}}
        publish_event(private)
        publish_event(mine)
        publish_event(public)
        assert receive(ws_a) == mine
        assert receive(ws_public) == public
        ws_a.send_json({'type': 'ping'})
        assert receive(ws_a) == {'type': 'pong'}  # nothing else was queued for A


def test_expired_token_closes_4401(raw_client):
    team = make_team('doi-a')
    now = int(time.time())
    expired = jwt.encode({'sub': str(team.member_id), 'role': 'member', 'typ': 'access', 'iat': now - 100,
                          'exp': now - 1}, 'test-secret-test-secret-test-secret-0001', algorithm='HS256')
    with raw_client.websocket_connect('/ws', headers=HEADERS) as ws:
        ws.send_json({'type': 'auth', 'access_token': expired})
        assert receive(ws)['code'] == 'TOKEN_EXPIRED'
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 4401


def test_token_expiry_during_connection_closes_4401(raw_client):
    team = make_team('doi-a')
    now = int(time.time())
    short = jwt.encode({'sub': str(team.member_id), 'role': 'member', 'typ': 'access', 'iat': now, 'exp': now + 2},
                       'test-secret-test-secret-test-secret-0001', algorithm='HS256')
    with raw_client.websocket_connect('/ws', headers=HEADERS) as ws:
        ws.send_json({'type': 'auth', 'access_token': short})
        assert receive(ws) == {'type': 'auth.ok'}
        assert receive(ws)['code'] == 'TOKEN_EXPIRED'
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 4401


def test_rate_limit_closes_4429(raw_client):
    with raw_client.websocket_connect('/ws', headers=HEADERS) as ws:
        for _ in range(30):
            ws.send_json({'type': 'ping'})
            receive(ws)
        ws.send_json({'type': 'ping'})
        assert receive(ws)['code'] == 'RATE_LIMITED'
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 4429


def test_idle_and_auth_window(raw_client, monkeypatch):
    import app.ws.router as wsr
    monkeypatch.setattr(wsr, 'IDLE_SECONDS', 1)
    with raw_client.websocket_connect('/ws', headers=HEADERS) as ws:
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 4408
    monkeypatch.setattr(wsr, 'IDLE_SECONDS', 60)
    monkeypatch.setattr(wsr, 'AUTH_WINDOW_SECONDS', 0)
    team = make_team('doi-a')
    with raw_client.websocket_connect('/ws', headers=HEADERS) as ws:
        time.sleep(0.05)
        ws.send_json({'type': 'auth', 'access_token': team.member['Authorization'].split()[1]})
        assert receive(ws)['code'] == 'UNAUTHORIZED'


def test_admin_can_subscribe_any_team(raw_client):
    team = make_team('doi-a')
    admin = make_admin()
    with raw_client.websocket_connect('/ws', headers=HEADERS) as ws:
        ws.send_json({'type': 'auth', 'access_token': admin['Authorization'].split()[1]})
        receive(ws)
        ws.send_json({'type': 'subscribe', 'channel': f'team:{team.id}'})
        assert receive(ws) == {'type': 'subscribed', 'channel': f'team:{team.id}'}
