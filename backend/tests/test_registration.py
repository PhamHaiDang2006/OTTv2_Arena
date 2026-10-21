import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import func, select

from app.db import session_scope
from app.models import Team, User
from app.security import REFRESH_COOKIE, verify_password
from tests.helpers import PASSWORD, PY_BOT, bearer, make_ready_submission, make_user, session_origin, upload, zip_bytes


def register(api, **changes):
    return api.post('/api/v1/auth/register', headers=session_origin(), idem=False,
                    json={'email': 'New@example.test', 'password': PASSWORD, 'team_name': ' Đội mới ', **changes})


def test_registration_session_team_and_permissions(api):
    response = register(api)
    assert response.status_code == 201
    auth = response.json()
    assert auth['user']['role'] == 'captain' and auth['user']['email'] == 'new@example.test'
    assert REFRESH_COOKIE in response.cookies
    headers = bearer(auth['access_token'])
    team = api.get('/api/v1/teams/me', headers=headers).json()
    assert team['name'] == 'Đội mới' and team['status'] == 'pending'
    assert len(team['members']) == 1 and team['members'][0]['id'] == auth['user']['id']
    assert api.get('/api/v1/admin/teams', headers=headers).status_code == 403
    with session_scope() as db:
        user = db.get(User, uuid.UUID(auth['user']['id']))
        assert user.password_hash != PASSWORD and verify_password(user.password_hash, PASSWORD)
    assert api.post('/api/v1/auth/refresh', headers=session_origin(), idem=False).status_code == 200
    assert api.post('/api/v1/auth/logout', headers=session_origin(), idem=False).status_code == 204
    assert api.post('/api/v1/auth/login', headers=session_origin(), idem=False,
                    json={'email': 'new@example.test', 'password': PASSWORD}).status_code == 200
    assert upload(api, headers, zip_bytes(PY_BOT)).status_code == 202


@pytest.mark.parametrize('changes', [{'password': 'short'}, {'password': 'x' * 257},
                                  {'email': 'invalid'}, {'team_name': '   '}, {'role': 'admin'},
                                  {'team_id': str(uuid.uuid4())}, {'status': 'approved'}])
def test_registration_rejects_invalid_input_without_creating_records(api, changes):
    response = register(api, **changes)
    assert response.status_code == 422
    assert PASSWORD not in response.text
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0
        assert db.scalar(select(func.count()).select_from(Team)) == 0


@pytest.mark.parametrize('password', [PASSWORD, None])
def test_existing_email_cannot_be_claimed_or_password_overwritten(api, password):
    user_id = make_user('new@example.test', password=password)
    assert register(api).status_code == 409
    with session_scope() as db:
        user = db.get(User, user_id)
        assert user.role == 'member'
        assert (user.password_hash is None) == (password is None)
        assert db.scalar(select(func.count()).select_from(Team)) == 0


def test_registration_origin_and_rate_limit(api):
    body = {'email': 'new@example.test', 'password': PASSWORD, 'team_name': 'Team'}
    assert api.post('/api/v1/auth/register', json=body, idem=False).status_code == 403
    assert api.post('/api/v1/auth/register', json=body, headers={'Origin': 'https://evil.test'},
                    idem=False).status_code == 403
    for i in range(5):
        assert register(api, email=f'new{i}@example.test').status_code == 201
    response = register(api, email='limited@example.test')
    assert response.status_code == 429 and 'retry-after' in response.headers


def test_self_registered_pending_teams_can_scrimmage(api):
    first = register(api).json()
    second = register(api, email='second@example.test').json()
    for auth in (first, second):
        make_ready_submission(uuid.UUID(auth['user']['team_id']))
    headers = bearer(first['access_token'])
    opponents = api.get('/api/v1/teams/opponents', headers=headers).json()['items']
    assert [t['id'] for t in opponents] == [second['user']['team_id']]
    response = api.post('/api/v1/scrimmages', headers=headers,
                        json={'opponent_team_id': second['user']['team_id']})
    assert response.status_code == 202


def test_concurrent_registration_creates_one_account_and_team(api, monkeypatch):
    from app.auth import router
    original = router.hash_password
    barrier = threading.Barrier(2)

    def synchronized_hash(password):
        value = original(password)
        barrier.wait(timeout=20)
        return value

    monkeypatch.setattr(router, 'hash_password', synchronized_hash)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: register(api), range(2)))
    assert sorted(r.status_code for r in responses) == [201, 409]
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(Team)) == 1


def test_registration_fails_closed_when_rate_limiter_unavailable(api, monkeypatch):
    from app import ratelimit

    def unavailable():
        raise RedisConnectionError('unavailable')

    monkeypatch.setattr(ratelimit, 'get_redis', unavailable)
    assert register(api).status_code == 503
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0
