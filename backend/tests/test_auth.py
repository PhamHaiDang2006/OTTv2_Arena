from __future__ import annotations

import time

import jwt

from app.security import REFRESH_COOKIE
from tests.helpers import PASSWORD, bearer, make_team, make_user, session_origin


def login(api, email: str, password: str = PASSWORD, origin: dict | None = None):
    return api.post('/api/v1/auth/login', json={'email': email, 'password': password},
                    headers=session_origin() if origin is None else origin, idem=False)


def test_login_returns_token_user_and_refresh_cookie(api):
    team = make_team('doi-a')
    response = login(api, 'Captain-Doi-A@example.test')
    assert response.status_code == 200
    body = response.json()
    assert body['token_type'] == 'bearer' and body['expires_in'] == 900
    assert body['user']['team_id'] == str(team.id) and body['user']['role'] == 'captain'
    cookie = response.headers['set-cookie']
    assert f'{REFRESH_COOKIE}=' in cookie and 'HttpOnly' in cookie and 'Path=/api/v1/auth' in cookie
    assert 'SameSite=strict' in cookie or 'SameSite=Strict' in cookie
    me = api.get('/api/v1/auth/me', headers=bearer(body['access_token'])).json()
    assert me['email'] == 'captain-doi-a@example.test'


def test_login_rejects_bad_credentials_inactive_and_passwordless(api):
    make_user('a@example.test')
    make_user('inactive@example.test', active=False)
    make_user('nopass@example.test', password=None)
    assert login(api, 'a@example.test', 'wrong-password').status_code == 401
    assert login(api, 'missing@example.test').status_code == 401
    assert login(api, 'inactive@example.test').status_code == 401
    assert login(api, 'nopass@example.test', 'ottv2-dummy-password').status_code == 401


def test_session_endpoints_require_allowed_origin(api):
    make_user('a@example.test')
    assert login(api, 'a@example.test', origin={}).status_code == 403
    assert login(api, 'a@example.test', origin={'Origin': 'https://evil.example'}).status_code == 403
    assert api.post('/api/v1/auth/refresh', idem=False).status_code == 403


def test_login_accepts_json_only(api):
    make_user('a@example.test')
    response = api.post('/api/v1/auth/login', data={'email': 'a@example.test', 'password': PASSWORD},
                        headers=session_origin(), idem=False)
    assert response.status_code == 422


def test_refresh_rotates_and_reuse_revokes_family(api):
    make_user('a@example.test')
    first = login(api, 'a@example.test').cookies[REFRESH_COOKIE]
    api.raw.cookies.clear()
    rotated = api.post('/api/v1/auth/refresh', headers=session_origin(), cookies={REFRESH_COOKIE: first}, idem=False)
    assert rotated.status_code == 200
    second = rotated.cookies[REFRESH_COOKIE]
    assert second != first
    api.raw.cookies.clear()
    # Re-using the rotated token revokes the family, so the newest token stops working too.
    assert api.post('/api/v1/auth/refresh', headers=session_origin(), cookies={REFRESH_COOKIE: first},
                    idem=False).status_code == 401
    api.raw.cookies.clear()
    assert api.post('/api/v1/auth/refresh', headers=session_origin(), cookies={REFRESH_COOKIE: second},
                    idem=False).status_code == 401


def test_refresh_without_cookie_is_401(api):
    assert api.post('/api/v1/auth/refresh', headers=session_origin(), idem=False).status_code == 401


def test_logout_revokes_and_is_idempotent(api):
    make_user('a@example.test')
    token = login(api, 'a@example.test').cookies[REFRESH_COOKIE]
    api.raw.cookies.clear()
    out = api.post('/api/v1/auth/logout', headers=session_origin(), cookies={REFRESH_COOKIE: token}, idem=False)
    assert out.status_code == 204
    assert 'Max-Age=0' in out.headers['set-cookie'] or 'expires=' in out.headers['set-cookie'].lower()
    api.raw.cookies.clear()
    assert api.post('/api/v1/auth/logout', headers=session_origin(), cookies={REFRESH_COOKIE: token},
                    idem=False).status_code == 204
    api.raw.cookies.clear()
    assert api.post('/api/v1/auth/refresh', headers=session_origin(), cookies={REFRESH_COOKIE: token},
                    idem=False).status_code == 401
    assert api.post('/api/v1/auth/logout', headers=session_origin(), idem=False).status_code == 401


def test_expired_and_forged_access_tokens(api):
    user_id = make_user('a@example.test')
    now = int(time.time())
    expired = jwt.encode({'sub': str(user_id), 'role': 'member', 'typ': 'access', 'iat': now - 1000, 'exp': now - 10},
                         'test-secret-test-secret-test-secret-0001', algorithm='HS256')
    forged = jwt.encode({'sub': str(user_id), 'role': 'admin', 'typ': 'access', 'iat': now, 'exp': now + 100},
                        'not-the-secret-not-the-secret-000000', algorithm='HS256')
    response = api.get('/api/v1/auth/me', headers=bearer(expired))
    assert response.status_code == 401 and response.json()['error']['details']['reason'] == 'token_expired'
    assert api.get('/api/v1/auth/me', headers=bearer(forged)).status_code == 401
    assert api.get('/api/v1/auth/me').status_code == 401


def test_deactivated_user_token_stops_working(api):
    from app.db import session_scope
    from app.models import User
    from tests.helpers import token_for
    user_id = make_user('a@example.test')
    headers = bearer(token_for(user_id))
    assert api.get('/api/v1/auth/me', headers=headers).status_code == 200
    with session_scope() as db:
        db.get(User, user_id).is_active = False
    assert api.get('/api/v1/auth/me', headers=headers).status_code == 401
