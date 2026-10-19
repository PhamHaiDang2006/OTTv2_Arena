"""Concurrent worker callbacks (4 match workers in production) must not lose round completion, duplicate
standings rows or deadlock."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from rq import Queue
from rq.job import Job
from sqlalchemy import func, select

from app.db import session_scope
from app.models import Game, Standing, WorkerJob
from app.queue import get_redis
from app.scheduler import watchdog_once
from tests.helpers import FakeWorker, job_for_game, make_ready_submission, make_team
from tests.test_tournament_flow import Tournament, reason, stronger_wins


def open_match_jobs():
    with session_scope() as db:
        return list(db.scalars(select(WorkerJob).where(WorkerJob.kind == 'match', WorkerJob.status != 'terminal')))


def play_concurrently(api, workers: int = 4) -> int:
    worker = FakeWorker(api)
    played = 0
    while jobs := open_match_jobs():
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(lambda job: worker.play(job.game_id, winner=stronger_wins(job, None)), jobs))
        played += len(jobs)
    return played


@pytest.mark.parametrize('repeat', range(3))
def test_concurrent_callbacks_complete_rounds(api, repeat):
    t = Tournament(api)
    t.post(f'/tournaments/{t.id}/draw', reason())
    t.post(f'/tournaments/{t.id}/draw/lock', reason())
    t.create_rounds()
    t.freeze('group')
    t.run('group')
    assert play_concurrently(api) == 8
    assert t.round('group')['status'] == 'finished'
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(Standing)) == 8
    assert all(s['team'] for s in t.bracket() if s['round'] == 'quarterfinal')
    t.freeze('quarterfinal')
    t.run('quarterfinal')
    assert play_concurrently(api) == 8  # 4 matches × 2 games (stronger seed wins both)
    assert t.round('quarterfinal')['status'] == 'finished'
    assert all(s['team'] for s in t.bracket() if s['round'] == 'semifinal')


def test_concurrent_duplicate_terminal_callbacks_count_once(api):
    a, b = make_team('doi-a'), make_team('doi-b')
    make_ready_submission(a.id)
    make_ready_submission(b.id)
    match_id = api.post('/api/v1/scrimmages', headers=a.member, json={'opponent_team_id': str(b.id)}).json()['match_id']
    game_id = api.get(f'/api/v1/matches/{match_id}', headers=a.member).json()['games'][0]['id']
    worker = FakeWorker(api)
    job = job_for_game(game_id)
    lease = worker.claim(job.id)
    body = worker.game_payload(job, 'finished', lease=lease)
    with ThreadPoolExecutor(max_workers=6) as pool:
        statuses = list(pool.map(lambda _: worker.post_game(game_id, body, lease).status_code, range(6)))
    assert statuses == [200] * 6
    match = api.get(f'/api/v1/matches/{match_id}', headers=a.member).json()
    assert match['score_a'] + match['score_b'] == 1


def test_watchdog_handles_rq_failure_before_lease(api):
    a, b = make_team('doi-a'), make_team('doi-b')
    make_ready_submission(a.id)
    make_ready_submission(b.id)
    match_id = api.post('/api/v1/scrimmages', headers=a.member, json={'opponent_team_id': str(b.id)}).json()['match_id']
    game_id = api.get(f'/api/v1/matches/{match_id}', headers=a.member).json()['games'][0]['id']
    job = job_for_game(game_id)
    rq_job = Job.fetch(str(job.id), connection=get_redis())
    Queue('match:scrimmage', connection=get_redis()).remove(rq_job)
    rq_job.set_status('failed')
    assert watchdog_once() == 1
    with session_scope() as db:
        first = db.get(Game, job.game_id)
        games = list(db.scalars(select(Game).where(Game.match_id == first.match_id, Game.game_index == 1)))
        assert sorted((g.attempt, g.status) for g in games) == [(1, 'infra_error'), (2, 'queued')]


def test_finished_callback_requires_stderr_logs(api):
    from app.storage import get_storage
    a, b = make_team('doi-a'), make_team('doi-b')
    make_ready_submission(a.id)
    make_ready_submission(b.id)
    match_id = api.post('/api/v1/scrimmages', headers=a.member, json={'opponent_team_id': str(b.id)}).json()['match_id']
    game_id = api.get(f'/api/v1/matches/{match_id}', headers=a.member).json()['games'][0]['id']
    worker = FakeWorker(api)
    job = job_for_game(game_id)
    lease = worker.claim(job.id)
    body = worker.game_payload(job, 'finished', lease=lease)
    get_storage().client.delete_object(Bucket=get_storage().bucket, Key=body['log_key'] + 'red.stderr.log')
    response = worker.post_game(game_id, body, lease)
    assert response.status_code == 422 and response.json()['error']['details']['reason'] == 'artifact_missing'


def test_tournament_callback_serializes_on_round_lock(api):
    """Deterministic check of the lock behind round completion: a finished callback for a group game must
    wait while another transaction holds the round row (concurrent callbacks are then serialized)."""
    import threading
    import time
    import uuid as _uuid

    from app.db import get_sessionmaker
    from app.models import Round
    t = Tournament(api)
    t.post(f'/tournaments/{t.id}/draw', reason())
    t.post(f'/tournaments/{t.id}/draw/lock', reason())
    t.create_rounds()
    t.freeze('group')
    t.run('group')
    with session_scope() as db:
        match_id = db.get(Game, open_match_jobs()[0].game_id).match_id
        first, second = db.scalars(select(Game.id).where(Game.match_id == match_id).order_by(Game.game_index)).all()
    worker = FakeWorker(api)
    worker.play(first)  # the second game's result completes the match → round-level work
    job = job_for_game(second)
    lease = worker.claim(job.id)
    assert worker.post_game(job.game_id, worker.game_payload(job, 'running'), lease).status_code == 200
    body = worker.game_payload(job, 'finished', lease=lease)
    holder = get_sessionmaker()()
    holder.execute(select(Round.id).where(Round.id == _uuid.UUID(t.rounds['group'])).with_for_update())
    result = {}
    thread = threading.Thread(target=lambda: result.setdefault('status', worker.post_game(job.game_id, body, lease)
                                                                .status_code))
    thread.start()
    time.sleep(0.7)
    assert thread.is_alive() and 'status' not in result
    holder.rollback()
    holder.close()
    thread.join(10)
    assert result['status'] == 200
