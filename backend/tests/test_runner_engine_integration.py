"""Real backend/RQ payloads, Redis leases, runner, engine and S3 adapter (moto).

Only Docker compilation/processes and the HTTP network are substituted. No fake
worker callbacks: RunnerRuntime produces every build/game result below.
"""
from __future__ import annotations

import gzip
import json
from urllib.parse import urlsplit

import pytest
from ottv2 import Board
from ottv2.adapter import make_engine
from ottv2_runner.config import Settings
from ottv2_runner.engine_verifier import EngineBuildVerifier, ReferenceBot
from ottv2_runner.errors import InfrastructureError
from ottv2_runner.http import HttpResponse
from ottv2_runner.jobs import configure_runtime
from ottv2_runner.runtime import RunnerRuntime
from ottv2_runner.storage import S3ObjectStore
from rq.job import Job

from app import contract
from app.db import session_scope
from app.models import Submission
from app.queue import get_redis
from app.storage import get_storage
from tests.helpers import make_admin, make_ready_submission, make_team, rq_job_ids, upload, zip_bytes


class Bot(ReferenceBot):
    stderr = b'integration stderr\n'
    debug = b''

    def __init__(self, failure=None):
        super().__init__()
        self.failure = failure
        self.closed = False

    async def read_line(self, timeout_ms):
        if self.failure == 'crash':
            raise EOFError
        if self.failure == 'infra':
            raise RuntimeError('test host pipe failure')
        return await super().read_line(timeout_ms)

    async def close(self):
        self.closed = True


class Sandbox:
    last_build_log = b'compiled\n'

    def __init__(self):
        self.failure = None
        self.bots = []
        self.builds = 0

    def build(self, language, source_dir, submission_id):
        assert (source_dir / 'main.py').is_file()
        self.last_build_log = b'compiled\n'
        self.builds += 1
        return 'registry.local/ottv2-bot@sha256:' + 'a' * 64

    def start_bot(self, image, cpu):
        bot = Bot(self.failure)
        self.bots.append(bot)
        return bot


class Transport:
    def __init__(self, api):
        self.api = api
        self.calls = []
        self.lose_terminal_response = False

    def post(self, url, payload, headers, timeout):
        try:
            response = self.api.post(urlsplit(url).path, json=payload, headers=headers, idem=False)
        except Exception as exc:
            raise InfrastructureError(str(exc)) from exc
        self.calls.append((url, payload, headers, response.status_code))
        if response.status_code >= 500:
            raise InfrastructureError(response.text)  # fail the test rather than retry forever
        if self.lose_terminal_response and payload['status'] in ('ready', 'finished') and response.status_code == 200:
            self.lose_terminal_response = False
            raise OSError('response lost after backend commit')
        return HttpResponse(response.status_code)


@pytest.fixture
def runtime(api, tmp_path):
    storage = get_storage()
    sandbox = Sandbox()
    settings = Settings(api_base_url='http://testserver/api/v1', worker_token='test-worker-token',
                        redis_url='unused', s3_endpoint_url='unused', s3_access_key='testing',
                        s3_secret_key='testing', s3_bucket=storage.bucket, outbox_dir=tmp_path / 'outbox',
                        worker_id='integration')
    runner = RunnerRuntime(settings, get_redis(), S3ObjectStore(storage.client, storage.bucket),
                           sandbox, Transport(api), engine_factory=make_engine,
                           build_verifier=EngineBuildVerifier(sandbox), work_dir=tmp_path / 'work')
    runner.callback_sender.sleep = lambda _: None
    configure_runtime(runner)
    yield runner
    configure_runtime(None)


def perform(job_id):
    # Exercise the actual string entrypoint and single dict argument enqueued by backend.
    return Job.fetch(job_id, connection=get_redis()).perform()


def pair(api):
    a, b = make_team('blue'), make_team('red')
    make_ready_submission(a.id)
    make_ready_submission(b.id)
    response = api.post('/api/v1/scrimmages', headers=a.member, json={'opponent_team_id': str(b.id)})
    assert response.status_code == 202
    return a, response.json()['match_id']


def test_upload_build_match_replay_and_duplicate_delivery(api, runtime):
    teams = [make_team('blue'), make_team('red')]
    for team in teams:
        response = upload(api, team.member, zip_bytes({'main.py': '# trusted test source\n'}))
        assert response.status_code == 202
        submission = response.json()['id']
        job_id = rq_job_ids('build')[-1]
        runtime.transport.lose_terminal_response = True
        callback = perform(job_id)
        assert callback['status'] == 'ready'
        assert not contract.errors('BuildResult', callback)
        assert api.get(f'/api/v1/submissions/{submission}', headers=team.member).json()['status'] == 'ready'
        assert get_storage().read(f'builds/{submission}/build.log')[0] == b'Build started\ncompiled\n'
        assert api.put('/api/v1/teams/me/active-bot', headers=team.captain,
                       json={'scope': 'scrimmage', 'submission_id': submission}).status_code == 200
        assert perform(job_id) is None  # same RQ job does not rebuild
    assert runtime.sandbox.builds == 2
    a, b = teams
    match_id = api.post('/api/v1/scrimmages', headers=a.member,
                        json={'opponent_team_id': str(b.id)}).json()['match_id']
    for job_id in rq_job_ids('match:scrimmage'):
        runtime.transport.lose_terminal_response = True
        result = perform(job_id)
        assert result['status'] == 'finished'
        assert not contract.errors('GameResultCallback', result)
        game_id = result['game_id']
        storage = get_storage()
        metadata = storage.head(f'replays/{game_id}.json.gz')
        assert metadata['ContentEncoding'] == 'gzip' and metadata['ContentType'] == 'application/json'
        replay = json.loads(gzip.decompress(storage.read(f'replays/{game_id}.json.gz')[0]))
        assert not contract.errors('Replay', replay)
        assert replay['result'] == result['result']
        assert len(replay['moves']) == result['result']['plies']
        board = Board.from_fen(replay['initial_fen'])
        for move in replay['moves']:
            assert move['move'] in board.legal_moves(move['side'])
            board.push(move['move'], move['side'])
        assert api.get(f'/api/v1/games/{game_id}/replay', headers=a.member).status_code == 200
        assert storage.read(f'logs/{game_id}/blue.stderr.log')[0] == Bot.stderr
        # An exact terminal retry still works after the runner releases its lease.
        url, payload, headers, _ = runtime.transport.calls[-1]
        assert runtime.transport.post(url, payload, headers, 1).status_code == 200
        assert perform(job_id) is None
    match = api.get(f'/api/v1/matches/{match_id}', headers=a.member).json()
    assert match['status'] == 'finished' and match['score_a'] + match['score_b'] == 2
    assert all(bot.closed for bot in runtime.sandbox.bots)
    assert all(call[3] == 200 for call in runtime.transport.calls)


@pytest.mark.parametrize('failure', ['crash', 'infra'])
def test_engine_failures_reach_backend_with_correct_attempt_and_logs(api, runtime, failure):
    team, match_id = pair(api)
    job_id = rq_job_ids('match:scrimmage')[0]
    runtime.sandbox.failure = failure
    callback = perform(job_id)
    assert not contract.errors('GameResultCallback', callback)
    admin = make_admin()
    logs = api.get(f'/api/v1/admin/games/{callback["game_id"]}/logs', headers=admin).json()
    assert logs['BLUE'] == Bot.stderr.decode()
    if failure == 'crash':
        assert callback['status'] == 'finished' and callback['result']['reason'] == 'CRASH'
    else:
        assert callback['status'] == 'infra_error' and callback['result'] is None
        games = api.get(f'/api/v1/matches/{match_id}', headers=team.member).json()['games']
        retried = next(g for g in games if g['game_index'] == 1 and g['is_current'])
        assert retried['attempt'] == 2 and retried['id'] != callback['game_id']
    assert all(bot.closed for bot in runtime.sandbox.bots)


def test_failed_smoke_build_is_accepted_as_failed_submission(api, runtime):
    team = make_team('broken')
    response = upload(api, team.member, zip_bytes({'main.py': '# broken test bot\n'}))
    runtime.sandbox.failure = 'crash'
    callback = perform(rq_job_ids('build')[0])
    assert callback['status'] == 'failed' and callback['image_tag'] is None
    assert api.get(f'/api/v1/submissions/{response.json()["id"]}', headers=team.member).json()['status'] == 'failed'


def test_scrimmage_rejects_bot_built_for_another_engine(api):
    a, b = make_team('blue'), make_team('red')
    submission = make_ready_submission(a.id)
    make_ready_submission(b.id)
    with session_scope() as db:
        db.get(Submission, submission).engine_version = '0.9.0'
    response = api.post('/api/v1/scrimmages', headers=a.member, json={'opponent_team_id': str(b.id)})
    assert response.status_code == 409
    assert response.json()['error']['details']['reason'] == 'engine_version_mismatch'
    assert rq_job_ids('match:scrimmage') == []
