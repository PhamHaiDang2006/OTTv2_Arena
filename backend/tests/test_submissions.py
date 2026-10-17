from __future__ import annotations

import io
import uuid
import zipfile

import pytest
from sqlalchemy import func, select

from app import contract
from app.db import session_scope
from app.models import Outbox, Submission
from app.storage import get_storage
from tests.helpers import (
    PY_BOT,
    FakeWorker,
    make_admin,
    make_team,
    open_jobs,
    rq_job_ids,
    rq_payload,
    upload,
    zip_bytes,
)


def test_upload_creates_queued_submission_build_job_and_source(api):
    team = make_team('doi-a')
    data = zip_bytes(PY_BOT)
    response = upload(api, team.member, data)
    assert response.status_code == 202
    submission_id = response.json()['id']
    assert response.json()['status'] == 'queued'
    jobs = rq_job_ids('build')
    assert len(jobs) == 1
    payload = rq_payload(jobs[0])
    assert not contract.errors('BuildJob', payload)
    assert payload['submission_id'] == submission_id and payload['job_id'] == jobs[0]
    assert payload['source_key'] == f'submissions/{submission_id}/source.zip'
    stored, _ = get_storage().read(payload['source_key'])
    assert stored == data
    detail = api.get(f'/api/v1/submissions/{submission_id}', headers=team.member).json()
    assert detail['status'] == 'queued' and detail['team_id'] == str(team.id)
    tree = api.get(f'/api/v1/submissions/{submission_id}/source', headers=team.member).json()
    assert [f['path'] for f in tree['files']] == ['main.py', 'util/helper.py']
    file = api.get(f'/api/v1/submissions/{submission_id}/source-file?path=main.py', headers=team.member).json()
    assert file['content'] == PY_BOT['main.py'] and file['truncated'] is False
    assert api.get(f'/api/v1/submissions/{submission_id}/source-file?path=nope.py',
                   headers=team.member).status_code == 404


def test_upload_same_key_same_body_returns_same_submission(api):
    team = make_team('doi-a')
    data = zip_bytes(PY_BOT)
    key = str(uuid.uuid4())
    first = upload(api, team.member, data, idem=key)
    second = upload(api, team.member, data, idem=key)
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert second.headers.get('Idempotent-Replay') == 'true'
    assert len(rq_job_ids('build')) == 1
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(Submission)) == 1
    other = upload(api, team.member, zip_bytes({'main.py': 'print(2)\n'}), idem=key)
    assert other.status_code == 409 and other.json()['error']['code'] == 'IDEMPOTENCY_CONFLICT'
    assert upload(api, team.member, data, language='cpp', idem=key).status_code in (409, 422)


def test_upload_requires_idempotency_key(api):
    team = make_team('doi-a')
    response = upload(api, team.member, zip_bytes(PY_BOT), idem=False)
    assert response.status_code == 422


def bad_zip_cases():
    deep = io.BytesIO()
    with zipfile.ZipFile(deep, 'w') as z:
        info = zipfile.ZipInfo('link.py')
        info.external_attr = (0o120777 << 16)
        z.writestr(info, 'main.py')
        z.writestr('main.py', 'x')
    return {
        'not_zip': b'hello',
        'traversal': zip_bytes({'main.py': 'x', '../evil.py': 'x'}),
        'absolute': zip_bytes({'main.py': 'x', '/etc/passwd.txt': 'x'}),
        'symlink': deep.getvalue(),
        'nested': zip_bytes({'main.py': 'x', 'inner.zip': zip_bytes({'a.py': 'x'})}),
        'binary': zip_bytes({'main.py': 'x', 'data.txt': b'\x00\x01\x02'}),
        'not_utf8': zip_bytes({'main.py': b'\xff\xfe\xfa'}),
        'bad_extension': zip_bytes({'main.py': 'x', 'run.sh': 'echo'}),
        'dockerfile': zip_bytes({'main.py': 'x', 'Dockerfile': 'FROM x'}),
        'missing_main': zip_bytes({'bot.py': 'x'}),
        'main_not_root': zip_bytes({'src/main.py': 'x'}),
        'duplicate': zip_bytes({'main.py': 'x', 'A.py': 'x', 'a.py': 'y'}),
        'too_many': zip_bytes({'main.py': 'x', **{f'f{i}.py': 'x' for i in range(50)}}),
        'unicode_name': zip_bytes({'main.py': 'x', 'thư.py': 'x'}),
    }


@pytest.mark.parametrize('case', sorted(bad_zip_cases()))
def test_upload_rejects_invalid_archives(api, case):
    team = make_team('doi-a')
    response = upload(api, team.member, bad_zip_cases()[case])
    assert response.status_code == 422, (case, response.json())
    assert response.json()['error']['code'] == 'INVALID_REQUEST'
    assert rq_job_ids('build') == []


def test_upload_size_limits(api):
    team = make_team('doi-a')
    big_file = zip_bytes({'main.py': 'x', 'big.txt': 'a' * (1024 * 1024 + 1)})
    assert upload(api, team.member, big_file).status_code == 413
    total = {f'part{i}.txt': f'{i:08d}' * 131072 for i in range(6)}  # 6 files × 1 MiB, compresses to almost nothing
    response = upload(api, team.member, zip_bytes({'main.py': 'x', **total}))
    assert response.status_code == 413 and response.json()['error']['details']['reason'] == 'total_too_large'
    stored = io.BytesIO()
    with zipfile.ZipFile(stored, 'w', zipfile.ZIP_STORED) as archive:
        archive.writestr('main.py', 'x')
        archive.writestr('a.txt', 'a' * 600_000)
        archive.writestr('b.txt', 'b' * 600_000)
    assert len(stored.getvalue()) > 1024 * 1024
    response = upload(api, team.member, stored.getvalue())
    assert response.status_code == 413 and response.json()['error']['details']['reason'] == 'zip_too_large'


def test_upload_language_and_form_validation(api):
    team = make_team('doi-a')
    data = zip_bytes({'Main.java': 'class Main {}'})
    response = upload(api, team.member, data, language='java')
    assert response.status_code == 422 and 'enabled' in response.json()['error']['details']
    assert upload(api, team.member, data, language='rust').status_code == 422
    assert api.post('/api/v1/submissions', headers=team.member, json={'language': 'python'}).status_code == 422
    cpp = upload(api, team.member, zip_bytes({'main.cpp': 'int main(){}', 'lib/x.hpp': '#pragma once'}), 'cpp')
    assert cpp.status_code == 202


def test_locked_disqualified_and_teamless_cannot_upload(api):
    locked = make_team('locked', locked=True)
    disq = make_team('disq', status='disqualified')
    admin = make_admin()
    assert upload(api, locked.member, zip_bytes(PY_BOT)).status_code == 409
    assert upload(api, disq.member, zip_bytes(PY_BOT)).status_code == 409
    assert upload(api, admin, zip_bytes(PY_BOT)).status_code == 403


def test_cross_team_access_is_not_found(api):
    a, b = make_team('doi-a'), make_team('doi-b')
    submission_id = upload(api, a.member, zip_bytes(PY_BOT)).json()['id']
    for suffix in ('', '/build-log', '/source', '/source-file?path=main.py'):
        assert api.get(f'/api/v1/submissions/{submission_id}{suffix}', headers=b.member).status_code == 404
    assert api.get('/api/v1/submissions', headers=b.member).json()['total'] == 0
    assert api.get('/api/v1/submissions', headers=a.member).json()['total'] == 1
    admin = make_admin()
    assert api.get(f'/api/v1/admin/submissions/{submission_id}/source', headers=admin).status_code == 200
    assert api.get(f'/api/v1/admin/submissions/{submission_id}/source', headers=a.member).status_code == 403


def test_build_callback_lifecycle_and_events(api):
    team = make_team('doi-a')
    submission_id = upload(api, team.member, zip_bytes(PY_BOT)).json()['id']
    job = open_jobs('build')[0]
    worker = FakeWorker(api)
    lease = worker.claim(job.id)
    response, _, _ = worker.build(job, status='building', lease=lease)
    assert response.status_code == 200 and response.json() == {'accepted': True}
    assert api.get(f'/api/v1/submissions/{submission_id}', headers=team.member).json()['status'] == 'building'
    response, body, _ = worker.build(job, status='ready', lease=lease, log_text='compiled\n')
    assert response.status_code == 200
    detail = api.get(f'/api/v1/submissions/{submission_id}', headers=team.member).json()
    assert detail['status'] == 'ready' and detail['build_error'] is None
    log = api.get(f'/api/v1/submissions/{submission_id}/build-log', headers=team.member).json()
    assert log['text'] == 'compiled\n' and log['status'] == 'ready'
    # The log was finalized to the canonical immutable key.
    assert get_storage().head(f'builds/{submission_id}/build.log') is not None
    # Retry of the identical terminal callback after lease release → 200, no second event.
    worker.release(job.id)
    assert worker.post_build(submission_id, body, lease).status_code == 200
    with session_scope() as db:
        events = [o.payload for o in db.scalars(select(Outbox).where(Outbox.kind == 'event').order_by(Outbox.id))]
    assert [(e['type'], e['data']['status'], e['channel']) for e in events] == [
        ('build.updated', 'building', f'team:{team.id}'), ('build.updated', 'ready', f'team:{team.id}')]
    for event in events:
        assert not contract.errors('WsEvent', event)
    # A different terminal payload, or a late `building`, is rejected.
    changed = {**body, 'image_tag': 'registry.local/other@sha256:' + 'd' * 64}
    assert worker.post_build(submission_id, changed, lease).status_code == 409
    late = {**body, 'status': 'building', 'image_tag': None, 'build_log_key': None}
    assert worker.post_build(submission_id, late, lease).status_code == 409


def test_build_failed_and_infra_error(api):
    team = make_team('doi-a')
    first = upload(api, team.member, zip_bytes(PY_BOT)).json()['id']
    second = upload(api, team.member, zip_bytes({'main.py': 'print(1)\n'})).json()['id']
    jobs = {str(j.submission_id): j for j in open_jobs('build')}
    worker = FakeWorker(api)
    worker.build(jobs[first], status='failed', error_code='COMPILE_ERROR')
    worker.build(jobs[second], status='failed', error_code='INFRA_ERROR')
    one = api.get(f'/api/v1/submissions/{first}', headers=team.member).json()
    two = api.get(f'/api/v1/submissions/{second}', headers=team.member).json()
    assert one['status'] == 'failed' and one['build_error']['code'] == 'COMPILE_ERROR'
    assert two['status'] == 'failed' and two['build_error']['code'] == 'INFRA_ERROR'
    assert open_jobs('build') == []


def test_build_callback_auth_lease_and_ids(api):
    team = make_team('doi-a')
    submission_id = upload(api, team.member, zip_bytes(PY_BOT)).json()['id']
    job = open_jobs('build')[0]
    worker = FakeWorker(api)
    body = {'schema_version': 1, 'job_id': str(job.id), 'submission_id': submission_id, 'status': 'building',
            'image_tag': None, 'build_log_key': None, 'error': None}
    url = f'/api/v1/internal/builds/{submission_id}'
    lease = str(uuid.uuid4())
    # No lease claimed in Redis → stale/unknown worker.
    assert api.post(url, json=body, headers={'Authorization': 'Bearer test-worker-token', 'X-Worker-Lease': lease},
                    idem=False).status_code == 409
    real = worker.claim(job.id)
    assert api.post(url, json=body, headers={'X-Worker-Lease': real}, idem=False).status_code == 401
    assert api.post(url, json=body, headers={**team.member, 'X-Worker-Lease': real}, idem=False).status_code == 401
    assert api.post(url, json=body, headers={'Authorization': 'Bearer test-worker-token'}, idem=False).status_code == 422
    other = f'/api/v1/internal/builds/{uuid.uuid4()}'
    assert api.post(other, json=body, headers={'Authorization': 'Bearer test-worker-token', 'X-Worker-Lease': real},
                    idem=False).status_code == 422
    assert worker.post_build(submission_id, {**body, 'extra': 1}, real).status_code == 422
    assert worker.post_build(submission_id, {**body, 'job_id': str(uuid.uuid4())}, real).status_code == 404
    assert worker.post_build(submission_id, body, real).status_code == 200


def test_ready_callback_requires_uploaded_log(api):
    team = make_team('doi-a')
    submission_id = upload(api, team.member, zip_bytes(PY_BOT)).json()['id']
    job = open_jobs('build')[0]
    worker = FakeWorker(api)
    lease = worker.claim(job.id)
    body = {'schema_version': 1, 'job_id': str(job.id), 'submission_id': submission_id, 'status': 'ready',
            'image_tag': 'registry.local/x@sha256:' + 'e' * 64, 'build_log_key': f'staging/{job.id}/missing.log',
            'error': None}
    response = worker.post_build(submission_id, body, lease)
    assert response.status_code == 422 and response.json()['error']['details']['reason'] == 'artifact_missing'
    assert api.get(f'/api/v1/submissions/{submission_id}', headers=team.member).json()['status'] == 'queued'


def test_active_bot_rules(api):
    a, b = make_team('doi-a'), make_team('doi-b')
    submission_id = upload(api, a.member, zip_bytes(PY_BOT)).json()['id']
    body = {'scope': 'scrimmage', 'submission_id': submission_id}
    assert api.put('/api/v1/teams/me/active-bot', headers=a.member, json=body).status_code == 403
    not_ready = api.put('/api/v1/teams/me/active-bot', headers=a.captain, json=body)
    assert not_ready.status_code == 409 and not_ready.json()['error']['code'] == 'SUBMISSION_NOT_READY'
    FakeWorker(api).build(open_jobs('build')[0], status='ready')
    ok = api.put('/api/v1/teams/me/active-bot', headers=a.captain, json=body)
    assert ok.status_code == 200 and ok.json() == {'team_id': str(a.id), **body}
    assert api.put('/api/v1/teams/me/active-bot', headers=b.captain, json=body).status_code == 404
    team = api.get('/api/v1/teams/me', headers=a.member).json()
    assert team['active_bots'] == [{'team_id': str(a.id), **body}]
