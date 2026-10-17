"""Outbox delivery and queue pause/resume under partial failures."""
from __future__ import annotations

from datetime import timedelta

import pytest
from rq import Queue
from sqlalchemy import func, select, update

from app.db import session_scope
from app.models import Outbox, QueueControl, WorkerJob
from app.queue import deliver, get_redis
from app.scheduler import drain_paused_once, watchdog_once
from app.timeutil import utcnow
from tests.helpers import PY_BOT, FakeWorker, make_admin, make_team, open_jobs, rq_job_ids, upload, zip_bytes


def pause(api, admin, name, paused, reason='x'):
    response = api.put('/api/v1/admin/queue', headers=admin, json={'name': name, 'paused': paused, 'reason': reason})
    assert response.status_code == 200, response.text
    return response


def submit(api, team, n: int) -> list[str]:
    return [upload(api, team.member, zip_bytes({**PY_BOT, 'n.txt': str(i)})).json()['id'] for i in range(n)]


def test_paused_rows_do_not_starve_other_deliveries():
    with session_scope() as db:
        db.add(QueueControl(name='match:scrimmage', paused=True))
        for _ in range(250):  # more than one delivery batch (LIMIT 200)
            db.add(Outbox(kind='job', target='match:scrimmage', job_id=None, payload={}))
        event = Outbox(kind='event', target='public', payload={'type': 'announcement.published', 'channel': 'public'})
        db.add(event)
        db.flush()
        event_id = event.id
    assert deliver() == 1
    with session_scope() as db:
        assert db.get(Outbox, event_id).delivered_at is not None
        assert db.scalar(select(func.count()).select_from(Outbox).where(Outbox.delivered_at.is_(None))) == 250


def test_delivery_never_pushes_a_waiting_job_twice(api):
    team = make_team('doi-a')
    submit(api, team, 1)
    [job_id] = rq_job_ids('build')
    with session_scope() as db:
        db.execute(update(Outbox).values(delivered_at=None))  # e.g. a drain marked it before failing
    assert deliver() == 1
    assert rq_job_ids('build') == [job_id]


def test_pause_drain_interrupted_midway_recovers_without_loss_or_duplicates(api, monkeypatch):
    admin = make_admin()
    team = make_team('doi-a')
    submit(api, team, 3)
    original = rq_job_ids('build')
    assert len(original) == 3
    calls = {'n': 0}
    real_remove = Queue.remove

    def flaky_remove(self, job_or_id, *args, **kwargs):
        calls['n'] += 1
        if calls['n'] > 1:
            raise ConnectionError('redis went away')
        return real_remove(self, job_or_id, *args, **kwargs)
    monkeypatch.setattr(Queue, 'remove', flaky_remove)
    pause(api, admin, 'build', True)  # pause is committed even though draining failed after one job
    monkeypatch.undo()
    assert len(rq_job_ids('build')) == 2
    log = api.get('/api/v1/admin/audit-log?action=queue.drain_incomplete', headers=admin).json()
    assert log['total'] == 1
    # Still paused: nothing is delivered; the scheduler finishes the drain.
    assert deliver() == 0
    assert drain_paused_once() == 2
    assert rq_job_ids('build') == []
    pause(api, admin, 'build', False)
    assert sorted(rq_job_ids('build')) == sorted(original)  # every job back exactly once


def test_resume_when_jobs_were_left_in_rq_does_not_duplicate(api, monkeypatch):
    admin = make_admin()
    team = make_team('doi-a')
    submit(api, team, 2)
    original = rq_job_ids('build')
    monkeypatch.setattr(Queue, 'remove', lambda self, *a, **k: (_ for _ in ()).throw(ConnectionError('down')))
    pause(api, admin, 'build', True)  # rows marked pending, nothing removed
    monkeypatch.undo()
    assert sorted(rq_job_ids('build')) == sorted(original)
    pause(api, admin, 'build', False)
    assert sorted(rq_job_ids('build')) == sorted(original)


def test_watchdog_redelivers_job_removed_from_queue_list(api):
    """The RQ hash survives but the id is in no queue list (old drain bug / manual LREM): redelivered once."""
    team = make_team('doi-a')
    submit(api, team, 1)
    [job_id] = rq_job_ids('build')
    Queue('build', connection=get_redis()).remove(job_id)
    with session_scope() as db:
        db.execute(update(WorkerJob).values(created_at=utcnow() - timedelta(minutes=10)))
    assert watchdog_once() == 0
    assert deliver() == 1
    assert rq_job_ids('build') == [job_id]


def test_watchdog_leaves_started_and_paused_jobs_alone(api):
    admin = make_admin()
    team = make_team('doi-a')
    submit(api, team, 1)
    [job] = open_jobs('build')
    FakeWorker(api).claim(job.id)
    Queue('build', connection=get_redis()).remove(str(job.id))  # a worker popped it and holds the lease
    with session_scope() as db:
        db.execute(update(WorkerJob).values(created_at=utcnow() - timedelta(minutes=10)))
    watchdog_once()
    assert deliver() == 0 and rq_job_ids('build') == []
    pause(api, admin, 'build', True)
    assert deliver() == 0


@pytest.mark.parametrize('paused', [True, False])
def test_pause_state_survives_in_queue_view(api, paused):
    admin = make_admin()
    body = pause(api, admin, 'match:tournament', paused).json()
    assert next(q for q in body['queues'] if q['name'] == 'match:tournament')['paused'] is paused
