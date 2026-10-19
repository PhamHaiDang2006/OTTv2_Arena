"""End-to-end smoke against a running backend (contracts/acceptance.md "Luồng smoke thật"), with this script
playing the worker side of the contract (Redis lease + S3 upload + callbacks). Not a substitute for the real
runner: no bot is built or run.

    uv run python scripts/smoke.py --api http://127.0.0.1:8000 --origin http://localhost:5173

Needs the same DATABASE_URL / REDIS_URL / S3_* / WORKER_API_TOKEN as the server, and `seed-dev` data
(admin@example.test, captain-doi-a@example.test, captain-doi-b@example.test, password in OTTV2_PASSWORD).
Every HTTP response and WebSocket frame is validated against contracts/.
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import io
import json
import os
import sys
import time
import uuid
import zipfile
from urllib.parse import urlsplit

import httpx
import websockets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import contract  # noqa: E402
from app.queue import get_redis, lease_key  # noqa: E402
from app.storage import get_storage  # noqa: E402

PASSWORD = os.environ.get('OTTV2_PASSWORD', '')
WORKER = {'Authorization': f'Bearer {os.environ.get("WORKER_API_TOKEN", "")}'}


def check(definition: str | None, response: httpx.Response, status: int) -> dict | None:
    if response.status_code != status:
        raise SystemExit(f'FAIL {response.request.method} {response.request.url}: {response.status_code} {response.text}')
    if definition:
        problems = contract.errors(definition, response.json())
        if problems:
            raise SystemExit(f'FAIL schema {definition}: {problems}')
        return response.json()
    return None


def step(text: str) -> None:
    print(f'✔ {text}', flush=True)


class Smoke:
    def __init__(self, api: str, origin: str):
        self.http = httpx.Client(base_url=api.rstrip('/') + '/api/v1', timeout=20)
        self.origin = origin
        self.ws_url = api.replace('http', 'ws', 1).rstrip('/') + '/ws'

    def login(self, email: str) -> dict[str, str]:
        client = httpx.Client(base_url=str(self.http.base_url), timeout=20)
        check('Auth', client.post('/auth/login', json={'email': email, 'password': PASSWORD},
                                  headers={'Origin': self.origin}), 200)
        assert 'ottv2_refresh' in client.cookies
        refreshed = check('Auth', client.post('/auth/refresh', headers={'Origin': self.origin}), 200)
        assert refreshed['user']['email'] == email
        return {'Authorization': f'Bearer {refreshed["access_token"]}'}

    def call(self, method: str, path: str, definition: str | None, status: int, headers=None, idem=True, **kw):
        headers = dict(headers or {})
        if idem and method != 'GET':
            headers['Idempotency-Key'] = idem if isinstance(idem, str) else str(uuid.uuid4())
        return check(definition, self.http.request(method, path, headers=headers, **kw), status)

    def wait_job(self, field: str, value: str, timeout: float = 10) -> dict:
        """Find the RQ job the backend enqueued (outbox → Redis), as a worker would."""
        from rq import Queue
        deadline = time.time() + timeout
        while time.time() < deadline:
            for name in ('build', 'match:tournament', 'match:scrimmage'):
                queue = Queue(name, connection=get_redis())
                for job in queue.jobs:
                    payload = job.args[0]
                    if payload.get(field) == value:
                        assert job.func_name in ('ottv2_runner.jobs.build_submission', 'ottv2_runner.jobs.run_match')
                        problems = contract.errors('BuildJob' if name == 'build' else 'MatchJob', payload)
                        assert not problems, problems
                        queue.remove(job)
                        return payload
            time.sleep(0.2)
        raise SystemExit(f'FAIL no job with {field}={value}')

    def lease(self, job_id: str) -> str:
        token = str(uuid.uuid4())
        assert get_redis().set(lease_key(job_id), token, nx=True, ex=90)
        return token

    def build(self, payload: dict) -> None:
        lease = self.lease(payload['job_id'])
        base = {'schema_version': 1, 'job_id': payload['job_id'], 'submission_id': payload['submission_id']}
        self.call('POST', f'/internal/builds/{payload["submission_id"]}', 'Ack', 200, idem=False,
                  headers={**WORKER, 'X-Worker-Lease': lease},
                  json={**base, 'status': 'building', 'image_tag': None, 'build_log_key': None, 'error': None})
        key = f'staging/{payload["job_id"]}/{lease}/build.log'
        get_storage().put(key, b'smoke build ok\n', 'text/plain')
        self.call('POST', f'/internal/builds/{payload["submission_id"]}', 'Ack', 200, idem=False,
                  headers={**WORKER, 'X-Worker-Lease': lease},
                  json={**base, 'status': 'ready', 'image_tag': f'registry.local/ottv2-bot@sha256:{"a" * 64}',
                        'build_log_key': key, 'error': None})
        get_redis().delete(lease_key(payload['job_id']))

    def play(self, payload: dict, winner: str) -> tuple[dict, str]:
        lease = self.lease(payload['job_id'])
        base = {'schema_version': 1, 'job_id': payload['job_id'], 'game_id': payload['game_id'],
                'attempt': payload['attempt']}
        headers = {**WORKER, 'X-Worker-Lease': lease}
        self.call('POST', f'/internal/games/{payload["game_id"]}', 'Ack', 200, idem=False, headers=headers,
                  json={**base, 'status': 'running', 'result': None, 'replay_key': None, 'log_key': None,
                        'duration_ms': 0, 'error': None})
        staging = f'staging/{payload["job_id"]}/{lease}/'
        replay = {'format': 1, 'engine_version': payload['engine_version'], 'ruleset_id': 'dev-v1', 'map_id': 'standard',
                  'initial_fen': payload['config']['initial_fen'],
                  'players': {side: {**payload['players'][side], 'bot_name': f'Smoke{side}'} for side in ('BLUE', 'RED')},
                  'moves': [], 'result': {'winner': winner, 'reason': 'CRASH', 'plies': 0}}
        assert not contract.errors('Replay', replay)
        storage = get_storage()
        storage.client.put_object(Bucket=storage.bucket, Key=staging + 'replay.json.gz',
                                  Body=gzip.compress(json.dumps(replay).encode()),
                                  ContentType='application/json', ContentEncoding='gzip')
        storage.put(staging + 'blue.stderr.log', b'blue says hi\n', 'text/plain')
        storage.put(staging + 'red.stderr.log', b'red says hi\n', 'text/plain')
        body = {**base, 'status': 'finished', 'result': replay['result'], 'replay_key': staging + 'replay.json.gz',
                'log_key': staging, 'duration_ms': 42, 'error': None}
        self.call('POST', f'/internal/games/{payload["game_id"]}', 'Ack', 200, idem=False, headers=headers, json=body)
        get_redis().delete(lease_key(payload['job_id']))
        return body, lease


async def listen(url: str, origin: str, token: str, team_id: str, sink: list) -> None:
    async with websockets.connect(url, origin=origin) as ws:
        for message in ({'type': 'auth', 'access_token': token}, {'type': 'subscribe', 'channel': f'team:{team_id}'}):
            await ws.send(json.dumps(message))
            reply = json.loads(await ws.recv())
            assert not contract.errors('WsServer', reply), reply
        sink.append('ready')
        while True:
            frame = json.loads(await ws.recv())
            assert not contract.errors('WsServer', frame), frame
            sink.append(frame)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--api', default='http://127.0.0.1:8000')
    parser.add_argument('--origin', default='http://localhost:5173')
    args = parser.parse_args()
    s = Smoke(args.api, args.origin)
    check('Health', s.http.get('/health'), 200)
    admin = s.login('admin@example.test')
    cap_a, cap_b = s.login('captain-doi-a@example.test'), s.login('captain-doi-b@example.test')
    team_a = s.call('GET', '/teams/me', 'Team', 200, cap_a)
    team_b = s.call('GET', '/teams/me', 'Team', 200, cap_b)
    step('login + refresh cookie for admin and two captains')

    events: list = []
    loop = asyncio.new_event_loop()
    import threading
    threading.Thread(target=lambda: loop.run_until_complete(
        listen(s.ws_url, args.origin, cap_a['Authorization'].split()[1], team_a['id'], events)), daemon=True).start()
    while 'ready' not in events:
        time.sleep(0.05)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('main.py', 'print("READY smoke", flush=True)\n')
    data = buffer.getvalue()
    subs = {}
    for name, headers in (('A', cap_a), ('B', cap_b)):
        key = str(uuid.uuid4())
        files = {'file': ('bot.zip', data, 'application/zip')}
        first = s.call('POST', '/submissions', 'SubmissionAccepted', 202, headers, idem=key, files=files,
                       data={'language': 'python'})
        again = s.call('POST', '/submissions', 'SubmissionAccepted', 202, headers, idem=key, files=files,
                       data={'language': 'python'})
        assert first == again
        subs[name] = first['id']
        s.build(s.wait_job('submission_id', first['id']))
        assert s.call('GET', f'/submissions/{first["id"]}', 'Submission', 200, headers)['status'] == 'ready'
        assert s.call('GET', f'/submissions/{first["id"]}/build-log', 'BuildLog', 200, headers)['text'] == 'smoke build ok\n'
        s.call('PUT', '/teams/me/active-bot', 'ActiveBot', 200, headers,
               json={'scope': 'scrimmage', 'submission_id': first['id']})
    step('upload ZIP (same key → same submission_id), build ready via worker callback, active bot set')

    accepted = s.call('POST', '/scrimmages', 'MatchAccepted', 202, cap_a, json={'opponent_team_id': team_b['id']})
    match = s.call('GET', f'/matches/{accepted["match_id"]}', 'Match', 200, cap_a)
    jobs = [s.wait_job('game_id', g['id']) for g in match['games']]
    results = [s.play(job, 'BLUE') for job in jobs]
    match = s.call('GET', f'/matches/{accepted["match_id"]}', 'Match', 200, cap_b)
    assert match['status'] == 'finished' and (match['score_a'], match['score_b']) == (1, 1)
    step('scrimmage: two side-swapped games finished, pair result 1–1')

    signed = s.call('GET', f'/games/{match["games"][0]["id"]}/replay', 'SignedUrl', 200, cap_b)
    replay_response = httpx.get(signed['url'])
    assert replay_response.status_code == 200, replay_response.text
    assert not contract.errors('Replay', replay_response.json())
    step(f'signed replay URL served by S3 ({urlsplit(signed["url"]).netloc}), gzip decoded once, schema valid')

    body, lease = results[0]
    s.call('POST', f'/internal/games/{body["game_id"]}', 'Ack', 200, idem=False,
           headers={**WORKER, 'X-Worker-Lease': lease}, json=body)
    again = s.call('GET', f'/matches/{accepted["match_id"]}', 'Match', 200, cap_a)
    assert (again['score_a'], again['score_b']) == (1, 1)
    logs = s.call('GET', f'/admin/games/{body["game_id"]}/logs', 'GameLogs', 200, admin)
    assert logs['BLUE'] == 'blue says hi\n'
    s.call('GET', f'/admin/games/{body["game_id"]}/logs', 'Error', 403, cap_a)
    step('duplicate callback did not change score; admin reads stderr, captain gets 403')

    deadline = time.time() + 5
    wanted = {'build.updated', 'game.finished', 'match.finished'}
    while time.time() < deadline and not wanted <= {e['type'] for e in events if isinstance(e, dict)}:
        time.sleep(0.1)
    seen = sorted({e['type'] for e in events if isinstance(e, dict)})
    assert wanted <= set(seen), seen
    step(f'WebSocket team channel received {seen}')
    print('SMOKE OK')


if __name__ == '__main__':
    main()
