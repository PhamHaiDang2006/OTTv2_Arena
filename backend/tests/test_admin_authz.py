from __future__ import annotations

import re
import uuid

import pytest
from sqlalchemy import func, select

from app import contract
from app.db import session_scope
from app.models import Outbox, Team, User
from app.queue import deliver
from tests.helpers import PY_BOT, WORKER, make_admin, make_ready_submission, make_team, rq_job_ids, upload, zip_bytes

SESSION_OPS = {'login', 'refresh', 'logout'}  # Origin/cookie rules tested in test_auth.py


def _request(op):
    path = '/api/v1' + re.sub(r'\{\w+\}', str(uuid.uuid4()), op['path'])
    if op['operationId'] in ('listMatches', 'getStandings', 'getBracket'):
        path += f'?tournament_id={uuid.uuid4()}'
    if op['operationId'] in ('getOwnSourceFile', 'adminGetSourceFile'):
        path += '?path=main.py'
    kwargs = {}
    if op['multipart']:
        kwargs = {'files': {'file': ('bot.zip', zip_bytes(PY_BOT), 'application/zip')}, 'data': {'language': 'python'}}
    elif op.get('request_example'):
        kwargs = {'json': contract.read_json(op['request_example'].removeprefix('contracts/'))}
    return op['method'].upper(), path, kwargs


@pytest.fixture
def roles():
    team = make_team('doi-a')
    return {'anonymous': {}, 'member': team.member, 'captain': team.captain, 'admin': make_admin(),
            'worker': dict(WORKER)}


ALLOWED = {'public': {'anonymous', 'member', 'captain', 'admin', 'worker'},
           'member': {'member', 'captain', 'admin'}, 'captain': {'captain', 'admin'}, 'admin': {'admin'},
           'worker': {'worker'}}


@pytest.mark.parametrize('op', [o for o in contract.operations() if o['operationId'] not in SESSION_OPS],
                         ids=lambda o: o['operationId'])
def test_role_matrix(api, roles, op):
    """Route-level authorization for every contract operation and the five caller kinds."""
    method, path, kwargs = _request(op)
    for role, headers in roles.items():
        extra = {'X-Worker-Lease': str(uuid.uuid4())} if op['role'] == 'worker' else {}
        response = api.request(method, path, headers={**headers, **extra}, **kwargs)
        status = response.status_code
        if role in ALLOWED[op['role']]:
            assert status not in (401, 403) or (role == 'admin' and op['operationId'] in (
                'createSubmission', 'createScrimmage', 'scrimmageQuota')), (role, status, response.text)
        elif role == 'anonymous' or op['role'] == 'worker' or (role == 'worker' and op['role'] != 'public'):
            assert status == 401, (role, status, response.text)
        else:
            assert status == 403, (role, status, response.text)


def test_admin_team_crud_and_seed_rules(api):
    admin = make_admin()
    body = {'name': 'Đội X', 'slug': 'doi-x', 'captain_email': 'Cap.X@example.test', 'seed': 4}
    created = api.post('/api/v1/admin/teams', headers=admin, json=body)
    assert created.status_code == 201
    team = created.json()
    assert team['status'] == 'pending' and team['members'][0]['email'] == 'cap.x@example.test'
    assert api.post('/api/v1/admin/teams', headers=admin, json=body).status_code == 409  # slug taken
    other = {**body, 'slug': 'doi-y', 'captain_email': 'y@example.test'}
    assert api.post('/api/v1/admin/teams', headers=admin, json=other).json()['error']['details']['reason'] == 'seed_taken'
    patch = api.patch(f'/api/v1/admin/teams/{team["id"]}', headers=admin,
                      json={'status': 'approved', 'is_locked': True, 'reason': 'duyệt'})
    assert patch.status_code == 200 and patch.json()['status'] == 'approved' and patch.json()['is_locked'] is True
    assert api.patch(f'/api/v1/admin/teams/{team["id"]}', headers=admin, json={'reason': 'x'}).status_code == 422
    log = api.get('/api/v1/admin/audit-log?action=team.update', headers=admin).json()['items'][0]
    assert log['payload']['before'] == {'status': 'pending', 'is_locked': False}
    listed = api.get('/api/v1/admin/teams', headers=admin).json()
    assert listed['total'] == 1
    # The new captain has no password: cannot log in until set via CLI.
    with session_scope() as db:
        assert db.scalar(select(User.password_hash).where(User.email == 'cap.x@example.test')) is None


def test_csv_import_is_all_or_nothing(api):
    admin = make_admin()
    make_team('taken')
    bad = ('name,slug,captain_email,seed\n'
           'Đội A,doi-a,a@example.test,1\n'
           'Đội B,taken,b@example.test,2\n'
           ',doi-c,not-an-email,x\n'
           'Đội D,doi-a,a@example.test,1\n')
    result = api.post('/api/v1/admin/teams/import', headers=admin, json={'csv': bad})
    assert result.status_code == 201
    body = result.json()
    assert body['created'] == []
    rows = {(e['row'], e['code']) for e in body['errors']}
    assert {(3, 'SLUG_TAKEN'), (4, 'INVALID_NAME'), (4, 'INVALID_EMAIL'), (4, 'INVALID_SEED'),
            (5, 'DUPLICATE_SLUG'), (5, 'DUPLICATE_EMAIL'), (5, 'DUPLICATE_SEED')} <= rows
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(Team)) == 1
    header = api.post('/api/v1/admin/teams/import', headers=admin, json={'csv': 'a,b\n1,2\n'}).json()
    assert header['errors'][0] == {'row': 1, 'code': 'INVALID_HEADER', 'message': header['errors'][0]['message']}
    good = 'name,slug,captain_email,seed\nĐội A,doi-a,a@example.test,1\nĐội B,doi-b,b@example.test,\n'
    ok = api.post('/api/v1/admin/teams/import', headers=admin, json={'csv': good}).json()
    assert [t['slug'] for t in ok['created']] == ['doi-a', 'doi-b'] and ok['errors'] == []


def test_announcements_draft_publish_once(api):
    admin = make_admin()
    created = api.post('/api/v1/admin/announcements', headers=admin, json={'title': 'Lịch', 'body': 'Nội dung'})
    assert created.status_code == 201 and created.json()['published_at'] is None
    aid = created.json()['id']
    assert api.get('/api/v1/announcements').json()['total'] == 0
    assert api.patch(f'/api/v1/admin/announcements/{aid}', headers=admin,
                     json={'title': 'Lịch mới', 'body': 'B'}).json()['title'] == 'Lịch mới'
    first = api.post(f'/api/v1/admin/announcements/{aid}/publish', headers=admin, json={'reason': 'đăng'}).json()
    second = api.post(f'/api/v1/admin/announcements/{aid}/publish', headers=admin, json={'reason': 'đăng'}).json()
    assert first['published_at'] and second['published_at'] == first['published_at']
    assert api.patch(f'/api/v1/admin/announcements/{aid}', headers=admin,
                     json={'title': 'X', 'body': 'Y'}).status_code == 409
    public = api.get('/api/v1/announcements').json()
    assert public['total'] == 1 and public['items'][0]['title'] == 'Lịch mới'
    with session_scope() as db:
        published = [o.payload for o in db.scalars(select(Outbox).where(Outbox.kind == 'event'))]
    assert [(e['type'], e['channel']) for e in published] == [('announcement.published', 'public')]


def test_queue_pause_holds_jobs_and_resume_delivers_same_ids(api):
    admin = make_admin()
    team = make_team('doi-a')
    paused = api.put('/api/v1/admin/queue', headers=admin, json={'name': 'build', 'paused': True, 'reason': 'bảo trì'})
    assert paused.status_code == 200
    assert next(q for q in paused.json()['queues'] if q['name'] == 'build')['paused'] is True
    upload(api, team.member, zip_bytes(PY_BOT))
    assert rq_job_ids('build') == []
    queue = api.get('/api/v1/admin/queue', headers=admin).json()
    assert next(q for q in queue['queues'] if q['name'] == 'build')['queued'] == 1
    with session_scope() as db:
        pending = db.scalar(select(Outbox).where(Outbox.kind == 'job'))
        job_id = str(pending.job_id)
        assert pending.delivered_at is None
    api.put('/api/v1/admin/queue', headers=admin, json={'name': 'build', 'paused': False, 'reason': 'xong'})
    assert rq_job_ids('build') == [job_id]


def test_pause_drains_unclaimed_rq_jobs(api):
    admin = make_admin()
    team = make_team('doi-a')
    upload(api, team.member, zip_bytes(PY_BOT))
    [job_id] = rq_job_ids('build')
    api.put('/api/v1/admin/queue', headers=admin, json={'name': 'build', 'paused': True, 'reason': 'dừng'})
    assert rq_job_ids('build') == []
    api.put('/api/v1/admin/queue', headers=admin, json={'name': 'build', 'paused': False, 'reason': 'chạy'})
    assert rq_job_ids('build') == [job_id]


def test_outbox_survives_redis_failure(api, monkeypatch):
    """DB commit succeeds while Redis is down: the job stays pending and is delivered later with the same id."""
    import app.queue as q
    team = make_team('doi-a')

    def broken(*args, **kwargs):
        raise ConnectionError('redis down')
    monkeypatch.setattr(q, 'enqueue', broken)
    response = upload(api, team.member, zip_bytes(PY_BOT))
    assert response.status_code == 202
    with session_scope() as db:
        entry = db.scalar(select(Outbox).where(Outbox.kind == 'job'))
        assert entry.delivered_at is None and entry.attempts == 1 and 'redis down' in entry.last_error
        job_id = str(entry.job_id)
    monkeypatch.undo()
    assert deliver() == 1
    assert rq_job_ids('build') == [job_id]
    assert deliver() == 0


def test_admin_source_and_submission_filters(api):
    admin = make_admin()
    a, b = make_team('doi-a'), make_team('doi-b')
    sid = make_ready_submission(a.id)
    make_ready_submission(b.id)
    assert api.get(f'/api/v1/admin/submissions?team_id={a.id}', headers=admin).json()['total'] == 1
    assert api.get('/api/v1/admin/submissions?status=failed', headers=admin).json()['total'] == 0
    tree = api.get(f'/api/v1/admin/submissions/{sid}/source', headers=admin).json()
    assert {f['path'] for f in tree['files']} == set(PY_BOT)
    content = api.get(f'/api/v1/admin/submissions/{sid}/source-file?path=util/helper.py', headers=admin).json()
    assert content['content'] == PY_BOT['util/helper.py']
    assert api.get(f'/api/v1/admin/submissions/{sid}/source-file?path=../etc/passwd',
                   headers=admin).status_code == 422
    assert api.get(f'/api/v1/admin/submissions/{sid}/source-file?path=/etc/passwd', headers=admin).status_code == 422


def test_similarity_after_freeze(api):
    from app.db import session_scope as scope
    from app.models import FrozenBot, Round, RoundSnapshot, Tournament
    from app.scheduler import similarity_once
    admin = make_admin()
    a, b, c = make_team('doi-a'), make_team('doi-b'), make_team('doi-c')
    code = 'def best(moves):\n    return max(moves, key=lambda m: m.score)\n' * 3
    s1 = make_ready_submission(a.id, files={'main.py': code})
    s2 = make_ready_submission(b.id, files={'main.py': code.replace('moves', 'options').replace('best', 'pick')})
    s3 = make_ready_submission(c.id, files={'main.py': 'import random\nprint(random.random())\n'})
    with scope() as db:
        tournament = Tournament(name='T', engine_version='1.0.0', ruleset_id='dev-v1')
        db.add(tournament)
        db.flush()
        rnd = Round(tournament_id=tournament.id, stage='group', status='frozen')
        db.add(rnd)
        db.flush()
        from app.timeutil import utcnow
        snap = RoundSnapshot(round_id=rnd.id, frozen_at=utcnow())
        db.add(snap)
        db.flush()
        for team, sub in ((a, s1), (b, s2), (c, s3)):
            db.add(FrozenBot(snapshot_id=snap.id, team_id=team.id, submission_id=sub))
    assert similarity_once() == 1
    assert similarity_once() == 0
    items = api.get('/api/v1/admin/similarity', headers=admin).json()['items']
    assert len(items) == 3
    scores = {frozenset((i['submission_a'], i['submission_b'])): i['score'] for i in items}
    assert scores[frozenset((str(s1), str(s2)))] == 1.0  # renamed identifiers only
    assert scores[frozenset((str(s1), str(s3)))] < 0.2
