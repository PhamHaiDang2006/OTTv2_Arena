"""Artifact fencing (contracts/behavior.md): only the current lease owner's staging area is promoted, canonical
keys are immutable, and a stale worker cannot get its artifacts accepted."""
from __future__ import annotations

import gzip
import uuid

import pytest

from app.storage import get_storage
from tests.helpers import PY_BOT, FakeWorker, job_for_game, make_ready_submission, make_team, open_jobs, upload, zip_bytes


@pytest.fixture
def game(api):
    a, b = make_team('doi-a'), make_team('doi-b')
    make_ready_submission(a.id)
    make_ready_submission(b.id)
    match_id = api.post('/api/v1/scrimmages', headers=a.member, json={'opponent_team_id': str(b.id)}).json()['match_id']
    game_id = api.get(f'/api/v1/matches/{match_id}', headers=a.member).json()['games'][0]['id']
    return a, game_id


def reason_of(response):
    return response.json()['error']['details'].get('reason')


def test_canonical_or_foreign_keys_are_rejected(api, game):
    team, game_id = game
    worker = FakeWorker(api)
    job = job_for_game(game_id)
    lease = worker.claim(job.id)
    body = worker.game_payload(job, 'finished', lease=lease)
    storage = get_storage()
    # Worker writes straight to the canonical key (as the shape-only contract fixture shows): not accepted.
    storage.put(f'replays/{game_id}.json.gz', gzip.compress(b'{}'), 'application/json')
    direct = worker.post_game(game_id, {**body, 'replay_key': f'replays/{game_id}.json.gz'}, lease)
    assert direct.status_code == 422 and reason_of(direct) == 'artifact_not_staged'
    # A forged canonical object would block the real promotion (409 artifact_conflict, see below); keeping
    # worker credentials out of canonical prefixes is a storage-policy matter for infra.
    storage.client.delete_object(Bucket=storage.bucket, Key=f'replays/{game_id}.json.gz')
    other_lease = f'staging/{job.id}/{uuid.uuid4()}/replay.json.gz'
    storage.put(other_lease, b'x')
    assert reason_of(worker.post_game(game_id, {**body, 'replay_key': other_lease}, lease)) == 'artifact_not_staged'
    other_job = f'staging/{uuid.uuid4()}/{lease}/replay.json.gz'
    storage.put(other_job, b'x')
    assert reason_of(worker.post_game(game_id, {**body, 'replay_key': other_job}, lease)) == 'artifact_not_staged'
    bare = f'staging/{job.id}/{lease}/'
    assert reason_of(worker.post_game(game_id, {**body, 'log_key': f'logs/{game_id}/'}, lease)) == 'artifact_not_staged'
    assert reason_of(worker.post_game(game_id, {**body, 'replay_key': bare}, lease)) == 'artifact_not_staged'
    assert api.get(f'/api/v1/games/{game_id}', headers=team.member).json()['status'] == 'queued'
    assert worker.post_game(game_id, body, lease).status_code == 200


def test_stale_worker_cannot_replace_accepted_artifacts(api, game):
    team, game_id = game
    worker = FakeWorker(api)
    job = job_for_game(game_id)
    old_lease = worker.claim(job.id)
    stale_body = worker.game_payload(job, 'finished', lease=old_lease)
    # Lease turns over (e.g. RQ redelivery): a new owner finishes the game.
    worker.release(job.id)
    new_lease = worker.claim(job.id)
    body = worker.game_payload(job, 'finished', winner='RED', lease=new_lease)
    assert worker.post_game(game_id, body, new_lease).status_code == 200
    accepted, _ = get_storage().read(f'replays/{game_id}.json.gz')
    # The stale owner's callback (its own staging, old token) is rejected and the canonical replay is unchanged.
    assert worker.post_game(game_id, stale_body, old_lease).status_code == 409
    assert worker.post_game(game_id, {**stale_body, 'replay_key': body['replay_key']}, old_lease).status_code == 409
    after, _ = get_storage().read(f'replays/{game_id}.json.gz')
    assert after == accepted
    assert api.get(f'/api/v1/games/{game_id}', headers=team.member).json()['result']['winner'] == 'RED'


def test_existing_canonical_with_other_content_is_conflict(api, game):
    _, game_id = game
    worker = FakeWorker(api)
    job = job_for_game(game_id)
    lease = worker.claim(job.id)
    body = worker.game_payload(job, 'finished', lease=lease)
    get_storage().put(f'replays/{game_id}.json.gz', b'something else', 'application/json')
    response = worker.post_game(game_id, body, lease)
    assert response.status_code == 409 and reason_of(response) == 'artifact_conflict'
    stored, _ = get_storage().read(f'replays/{game_id}.json.gz')
    assert stored == b'something else'


def test_identical_canonical_copy_is_accepted_on_retry(api, game):
    """Promotion happened but the transaction failed: the retried callback finds an identical canonical copy."""
    _, game_id = game
    worker = FakeWorker(api)
    job = job_for_game(game_id)
    lease = worker.claim(job.id)
    body = worker.game_payload(job, 'finished', lease=lease)
    storage = get_storage()
    storage.copy(body['replay_key'], f'replays/{game_id}.json.gz', storage.head(body['replay_key'])['ETag'])
    assert worker.post_game(game_id, body, lease).status_code == 200


def test_build_log_must_be_staged(api):
    team = make_team('doi-a')
    submission_id = upload(api, team.member, zip_bytes(PY_BOT)).json()['id']
    job = open_jobs('build')[0]
    worker = FakeWorker(api)
    lease = worker.claim(job.id)
    get_storage().put(f'builds/{submission_id}/build.log', b'forged')
    body = {'schema_version': 1, 'job_id': str(job.id), 'submission_id': submission_id, 'status': 'failed',
            'image_tag': None, 'build_log_key': f'builds/{submission_id}/build.log',
            'error': {'code': 'COMPILE_ERROR', 'message': 'x'}}
    response = worker.post_build(submission_id, body, lease)
    assert response.status_code == 422 and reason_of(response) == 'artifact_not_staged'
    assert api.get(f'/api/v1/submissions/{submission_id}', headers=team.member).json()['status'] == 'queued'
