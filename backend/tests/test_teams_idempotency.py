from __future__ import annotations

import threading
import uuid

from sqlalchemy import func, select, text

from app.db import get_sessionmaker, session_scope
from app.idempotency import _lock_id
from app.models import IdempotencyRecord
from tests.helpers import make_admin, make_ready_submission, make_team


def test_my_team_and_admin_without_team(api):
    team = make_team('doi-a', seed=3)
    body = api.get('/api/v1/teams/me', headers=team.member).json()
    assert body['id'] == str(team.id) and body['seed'] == 3 and body['group_id'] is None
    assert {m['role'] for m in body['members']} == {'captain', 'member'}
    assert api.get('/api/v1/teams/me', headers=make_admin()).status_code == 404
    assert api.get('/api/v1/teams/me').status_code == 401


def test_update_my_team_captain_only(api):
    team = make_team('doi-a')
    assert api.patch('/api/v1/teams/me', headers=team.member, json={'name': 'X'}).status_code == 403
    response = api.patch('/api/v1/teams/me', headers=team.captain, json={'name': 'Đội Mới'})
    assert response.status_code == 200 and response.json()['name'] == 'Đội Mới'
    assert api.patch('/api/v1/teams/me', headers=team.captain, json={'name': '   '}).status_code == 422
    assert api.patch('/api/v1/teams/me', headers=team.captain, json={'name': 'A', 'slug': 'x'}).status_code == 422


def test_opponents_only_eligible_teams(api):
    me, ready, no_bot = make_team('me'), make_team('ready'), make_team('nobot')
    locked, pending = make_team('locked', locked=True), make_team('pending', status='pending')
    for t in (me, ready, locked, pending):
        make_ready_submission(t.id)
    make_ready_submission(no_bot.id, active=())
    slugs = [t['slug'] for t in api.get('/api/v1/teams/opponents', headers=me.member).json()['items']]
    assert set(slugs) == {'ready', 'pending'}


def test_idempotency_scope_is_actor_and_path(api):
    a, b = make_team('doi-a'), make_team('doi-b')
    key = str(uuid.uuid4())
    assert api.patch('/api/v1/teams/me', headers=a.captain, json={'name': 'A1'}, idem=key).status_code == 200
    # Same key from another actor is a different scope.
    assert api.patch('/api/v1/teams/me', headers=b.captain, json={'name': 'B1'}, idem=key).status_code == 200
    replay = api.patch('/api/v1/teams/me', headers=a.captain, json={'name': 'A1'}, idem=key)
    assert replay.json()['name'] == 'A1' and replay.headers['Idempotent-Replay'] == 'true'
    assert api.patch('/api/v1/teams/me', headers=a.captain, json={'name': 'A2'}, idem=key).status_code == 409
    bad = api.patch('/api/v1/teams/me', headers=a.captain, json={'name': 'A1'}, idem='not-a-uuid')
    assert bad.status_code == 422


def test_failed_request_does_not_store_idempotency(api):
    team = make_team('doi-a')
    key = str(uuid.uuid4())
    body = {'scope': 'scrimmage', 'submission_id': str(uuid.uuid4())}
    assert api.put('/api/v1/teams/me/active-bot', headers=team.captain, json=body, idem=key).status_code == 404
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(IdempotencyRecord)) == 0


def test_request_in_progress_while_same_key_is_locked(api):
    team = make_team('doi-a')
    key = str(uuid.uuid4())
    from app.db import session_scope as scope
    with scope() as db:
        captain_id = db.execute(text("SELECT id FROM users WHERE email = 'captain-doi-a@example.test'")).scalar()
    lock = _lock_id(str(captain_id), 'PATCH', '/api/v1/teams/me', key)
    holder = get_sessionmaker()()
    holder.execute(select(func.pg_advisory_xact_lock(lock)))
    try:
        response = api.patch('/api/v1/teams/me', headers=team.captain, json={'name': 'X'}, idem=key)
        assert response.status_code == 409 and response.json()['error']['code'] == 'REQUEST_IN_PROGRESS'
    finally:
        holder.rollback()
        holder.close()
    assert api.patch('/api/v1/teams/me', headers=team.captain, json={'name': 'X'}, idem=key).status_code == 200


def test_concurrent_duplicates_create_one_effect(api):
    team = make_team('doi-a')
    opponent = make_team('doi-b')
    make_ready_submission(team.id)
    make_ready_submission(opponent.id)
    key = str(uuid.uuid4())
    results = []

    def call():
        results.append(api.post('/api/v1/scrimmages', headers=team.member, idem=key,
                                json={'opponent_team_id': str(opponent.id)}))
    threads = [threading.Thread(target=call) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    statuses = sorted(r.status_code for r in results)
    assert set(statuses) <= {202, 409}
    assert len({r.json()['match_id'] for r in results if r.status_code == 202}) == 1
    assert all(r.json()['error']['code'] == 'REQUEST_IN_PROGRESS' for r in results if r.status_code == 409)
    assert api.get('/api/v1/scrimmages', headers=team.member).json()['total'] == 1
