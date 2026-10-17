"""Factories and a fake worker for tests. Data goes through the API where behaviour matters and directly into
the database only for preconditions (e.g. a ready submission without running a real build)."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import uuid
import zipfile
from typing import Any

from rq import Queue
from sqlalchemy import select

from app import contract
from app.db import session_scope
from app.models import ActiveBot, Submission, Team, TeamMember, User, WorkerJob
from app.queue import get_redis, lease_key
from app.security import hash_password, issue_access_token
from app.storage import get_storage, submission_source_key
from tests.conftest import ORIGIN

PASSWORD = 'correct horse battery'
WORKER = {'Authorization': 'Bearer test-worker-token'}


def bearer(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def make_user(email: str, role: str = 'member', password: str | None = PASSWORD, team_id=None,
              active: bool = True) -> uuid.UUID:
    with session_scope() as db:
        user = User(email=email, role=role, password_hash=hash_password(password) if password else None,
                    is_active=active)
        db.add(user)
        db.flush()
        if team_id is not None:
            db.add(TeamMember(team_id=team_id, user_id=user.id))
        return user.id


def token_for(user_id: uuid.UUID) -> str:
    with session_scope() as db:
        user = db.get(User, user_id)
        return issue_access_token(user.id, user.role)


class TeamCtx:
    def __init__(self, team_id: uuid.UUID, slug: str, captain_id: uuid.UUID, member_id: uuid.UUID):
        self.id, self.slug, self.captain_id, self.member_id = team_id, slug, captain_id, member_id
        self.captain = bearer(token_for(captain_id))
        self.member = bearer(token_for(member_id))


def make_team(slug: str, seed: int | None = None, status: str = 'approved', locked: bool = False) -> TeamCtx:
    with session_scope() as db:
        team = Team(name=f'Đội {slug}', slug=slug, seed=seed, status=status, is_locked=locked)
        db.add(team)
        db.flush()
        team_id = team.id
    captain = make_user(f'captain-{slug}@example.test', 'captain', team_id=team_id)
    member = make_user(f'member-{slug}@example.test', 'member', team_id=team_id)
    return TeamCtx(team_id, slug, captain, member)


def make_admin(email: str = 'admin@example.test') -> dict[str, str]:
    return bearer(token_for(make_user(email, 'admin')))


def zip_bytes(files: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


PY_BOT = {'main.py': 'import sys\nprint("READY bot", flush=True)\n', 'util/helper.py': 'X = 1\n'}


def make_ready_submission(team_id: uuid.UUID, language: str = 'python', active: tuple[str, ...] = ('scrimmage',),
                          files: dict[str, str] | None = None) -> uuid.UUID:
    """A built submission (precondition for matches), stored like a real upload."""
    data = zip_bytes(files or PY_BOT)
    submission_id = uuid.uuid4()
    key = submission_source_key(str(submission_id))
    get_storage().put(key, data, 'application/zip')
    manifest = [{'path': p, 'size_bytes': len(c.encode()), 'language': 'python'} for p, c in sorted((files or PY_BOT).items())]
    with session_scope() as db:
        db.add(Submission(id=submission_id, team_id=team_id, language=language, source_key=key,
                          sha256=hashlib.sha256(data).hexdigest(), source_manifest=manifest, status='ready',
                          image_tag=f'registry.local/ottv2-bot@sha256:{hashlib.sha256(str(submission_id).encode()).hexdigest()}',
                          engine_version='1.0.0'))
        db.flush()
        for scope in active:
            db.merge(ActiveBot(team_id=team_id, scope=scope, submission_id=submission_id))
    return submission_id


def upload(api, headers: dict[str, str], data: bytes, language: str = 'python', idem: str | bool = True):
    return api.post('/api/v1/submissions', headers=headers, idem=idem,
                    files={'file': ('bot.zip', data, 'application/zip')}, data={'language': language})


def rq_job_ids(queue_name: str) -> list[str]:
    return Queue(queue_name, connection=get_redis()).get_job_ids()


def rq_payload(job_id: str) -> dict[str, Any]:
    from rq.job import Job
    job = Job.fetch(job_id, connection=get_redis())
    return job.args[0]


def open_jobs(kind: str | None = None) -> list[WorkerJob]:
    with session_scope() as db:
        query = select(WorkerJob).where(WorkerJob.status != 'terminal').order_by(WorkerJob.created_at)
        if kind:
            query = query.where(WorkerJob.kind == kind)
        return list(db.scalars(query))


def job_for_game(game_id) -> WorkerJob:
    with session_scope() as db:
        return db.scalar(select(WorkerJob).where(WorkerJob.game_id == uuid.UUID(str(game_id))))


class FakeWorker:
    """Plays the runner side of the contract: lease in Redis, artifacts in S3, callbacks over HTTP."""

    def __init__(self, api):
        self.api = api

    def claim(self, job_id) -> str:
        token = str(uuid.uuid4())
        assert get_redis().set(lease_key(job_id), token, nx=True, ex=90)
        return token

    def release(self, job_id) -> None:
        get_redis().delete(lease_key(job_id))

    def build(self, job: WorkerJob, status: str = 'ready', lease: str | None = None, error_code: str = 'COMPILE_ERROR',
              log_text: str = 'build ok\n'):
        lease = lease or self.claim(job.id)
        log_key = f'staging/{job.id}/{lease}/build.log'
        get_storage().put(log_key, log_text.encode(), 'text/plain')
        body = {'schema_version': 1, 'job_id': str(job.id), 'submission_id': str(job.submission_id),
                'status': status, 'image_tag': None, 'build_log_key': log_key, 'error': None}
        if status == 'ready':
            body['image_tag'] = f'registry.local/ottv2-bot@sha256:{"c" * 64}'
        elif status == 'failed':
            body['error'] = {'code': error_code, 'message': 'Build failed'}
        elif status == 'building':
            body['build_log_key'] = None
        return self.post_build(job.submission_id, body, lease), body, lease

    def post_build(self, submission_id, body, lease):
        return self.api.post(f'/api/v1/internal/builds/{submission_id}', json=body,
                             headers={**WORKER, 'X-Worker-Lease': lease}, idem=False)

    def game_payload(self, job: WorkerJob, status: str, winner: str = 'BLUE', plies: int = 1,
                     reason: str = 'GOAL', lease: str = '') -> dict[str, Any]:
        body = {'schema_version': 1, 'job_id': str(job.id), 'game_id': str(job.game_id), 'attempt': job.attempt,
                'status': status, 'result': None, 'replay_key': None, 'log_key': None, 'duration_ms': 0, 'error': None}
        if status == 'finished':
            staging = f'staging/{job.id}/{lease}/'
            replay = {'format': 1, 'engine_version': '1.0.0', 'ruleset_id': 'dev-v1', 'map_id': 'standard',
                      'initial_fen': contract.INITIAL_FEN, 'players': {
                          'BLUE': {**job.payload['players']['BLUE'], 'bot_name': 'Blue'},
                          'RED': {**job.payload['players']['RED'], 'bot_name': 'Red'}},
                      'moves': [], 'result': {'winner': winner, 'reason': reason, 'plies': plies}}
            get_storage().put(staging + 'replay.json.gz', gzip.compress(json.dumps(replay).encode()), 'application/json')
            get_storage().put(staging + 'blue.stderr.log', b'blue stderr\n', 'text/plain')
            get_storage().put(staging + 'red.stderr.log', b'red stderr\n', 'text/plain')
            body.update(result={'winner': winner, 'reason': reason, 'plies': plies},
                        replay_key=staging + 'replay.json.gz', log_key=staging, duration_ms=1234)
        elif status == 'infra_error':
            body.update(duration_ms=10, error={'code': 'INFRA_ERROR', 'message': 'Docker unavailable'})
        return body

    def post_game(self, game_id, body, lease):
        return self.api.post(f'/api/v1/internal/games/{game_id}', json=body,
                             headers={**WORKER, 'X-Worker-Lease': lease}, idem=False)

    def play(self, game_id, winner: str = 'BLUE', plies: int = 10, release: bool = True):
        """Run one game to the end: claim, running, finished."""
        job = job_for_game(game_id)
        lease = self.claim(job.id)
        assert self.post_game(game_id, self.game_payload(job, 'running'), lease).status_code == 200
        body = self.game_payload(job, 'finished', winner=winner, plies=plies, lease=lease)
        response = self.post_game(game_id, body, lease)
        assert response.status_code == 200, response.text
        if release:
            self.release(job.id)
        return body, lease

    def infra(self, game_id):
        job = job_for_game(game_id)
        lease = self.claim(job.id)
        response = self.post_game(game_id, self.game_payload(job, 'infra_error'), lease)
        assert response.status_code == 200, response.text
        self.release(job.id)


def session_origin() -> dict[str, str]:
    return {'Origin': ORIGIN}
