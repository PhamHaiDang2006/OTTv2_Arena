"""Scrimmage admission (contract 1.3.0): per-team active limit and the global pause while tournament games or a
scrimmage backlog are pending. Already accepted scrimmages keep their jobs; nothing is cancelled or moved."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select, update

from app.config import get_settings
from app.db import session_scope
from app.models import Match, WorkerJob
from tests.helpers import FakeWorker, make_admin, make_ready_submission, make_team, rq_job_ids
from tests.test_tournament_flow import Tournament, play_all, reason

SCRIMMAGES = '/api/v1/scrimmages'


@pytest.fixture
def limits(monkeypatch):
    settings = get_settings()

    def set_limits(**values):
        for name, value in values.items():
            monkeypatch.setattr(settings, name, value)
    return set_limits


def ready_teams(*slugs):
    teams = [make_team(slug) for slug in slugs]
    for team in teams:
        make_ready_submission(team.id)
    return teams


def create(api, team, opponent):
    return api.post(SCRIMMAGES, headers=team.member, json={'opponent_team_id': str(opponent.id)})


def quota(api, team):
    return api.get(f'{SCRIMMAGES}/quota', headers=team.member).json()


def scrimmage_jobs():
    with session_scope() as db:
        return db.scalar(select(func.count()).select_from(WorkerJob).where(WorkerJob.queue == 'match:scrimmage'))


def test_quota_reports_active_matches_and_admission(api):
    a, b = ready_teams('doi-a', 'doi-b')
    assert quota(api, a) | {'resets_at': None} == {
        'limit': 60, 'used': 0, 'remaining': 60, 'resets_at': None, 'active': 0,
        'active_limit': get_settings().scrimmage_max_active_per_team,
        'admission': {'accepting': True, 'paused_reason': None}}
    assert create(api, a, b).status_code == 202
    body = quota(api, a)
    assert (body['used'], body['active']) == (1, 1)
    assert quota(api, b)['active'] == 0  # the opponent did not create it


def test_team_active_limit_counts_unfinished_matches_only(api, limits):
    limits(scrimmage_max_active_per_team=1)
    a, b = ready_teams('doi-a', 'doi-b')
    first = create(api, a, b)
    assert first.status_code == 202
    second = create(api, a, b)
    assert second.status_code == 429
    assert second.json()['error']['code'] == 'SCRIMMAGE_LIMIT'
    assert second.json()['error']['details'] == {'active': 1, 'active_limit': 1}
    assert quota(api, a)['used'] == 1  # refused requests do not consume the daily quota
    assert create(api, b, a).status_code == 202  # the other team has its own slot

    worker = FakeWorker(api)
    for game in api.get(f'/api/v1/matches/{first.json()["match_id"]}', headers=a.member).json()['games']:
        worker.play(game['id'])
    assert create(api, a, b).status_code == 202

    with session_scope() as db:  # a blocked match waits for an admin and frees the slot
        db.execute(update(Match).where(Match.created_by_team_id == a.id, Match.status != 'finished')
                   .values(status='blocked'))
    assert create(api, a, b).status_code == 202


def test_tournament_games_pause_new_scrimmages_but_keep_accepted_ones(api, limits):
    t = Tournament(api)
    a, b = t.teams[0], t.teams[1]
    accepted = create(api, a, b)
    assert accepted.status_code == 202
    queued_before = sorted(rq_job_ids('match:scrimmage'))
    assert len(queued_before) == 2

    assert t.post(f'/tournaments/{t.id}/draw', reason()).status_code == 200
    assert t.post(f'/tournaments/{t.id}/draw/lock', reason()).status_code == 200
    t.create_rounds()
    t.freeze('group')
    t.run('group')

    refused = create(api, b, a)
    assert refused.status_code == 503
    assert refused.json()['error']['code'] == 'SCRIMMAGE_PAUSED'
    assert refused.json()['error']['details'] == {'reason': 'tournament_load'}
    assert refused.headers['Retry-After'] == '60'
    assert quota(api, b)['admission'] == {'accepting': False, 'paused_reason': 'tournament_load'}
    assert quota(api, b)['used'] == 0
    # The scrimmage accepted before the round still waits on its own queue, untouched.
    assert sorted(rq_job_ids('match:scrimmage')) == queued_before
    assert scrimmage_jobs() == 2

    limits(scrimmage_pause_tournament_jobs=0)  # 0 disables the tournament trigger
    assert quota(api, b)['admission']['accepting'] is True
    limits(scrimmage_pause_tournament_jobs=1)

    play_all(api)  # every tournament and scrimmage game finishes
    assert quota(api, b)['admission'] == {'accepting': True, 'paused_reason': None}
    assert create(api, b, a).status_code == 202


def test_scrimmage_backlog_pauses_until_games_start(api, limits):
    limits(scrimmage_max_pending_games=2)
    a, b, c = ready_teams('doi-a', 'doi-b', 'doi-c')
    assert create(api, a, b).status_code == 202  # two queued games reach the threshold
    refused = create(api, c, a)
    assert refused.status_code == 503
    assert refused.json()['error']['details'] == {'reason': 'scrimmage_backlog'}
    with session_scope() as db:  # workers claimed both games: no longer waiting
        db.execute(update(WorkerJob).where(WorkerJob.queue == 'match:scrimmage').values(status='running'))
    assert create(api, c, a).status_code == 202


def test_admin_queue_pause_refuses_new_scrimmages_and_is_visible(api):
    admin = make_admin()
    a, b = ready_teams('doi-a', 'doi-b')
    assert api.get('/api/v1/admin/queue', headers=admin).json()['scrimmage_admission'] == {
        'accepting': True, 'paused_reason': None}
    paused = api.put('/api/v1/admin/queue', headers=admin,
                     json={'name': 'match:scrimmage', 'paused': True, 'reason': 'bảo trì'})
    assert paused.status_code == 200
    assert paused.json()['scrimmage_admission'] == {'accepting': False, 'paused_reason': 'queue_paused'}
    refused = create(api, a, b)
    assert refused.status_code == 503 and refused.json()['error']['details'] == {'reason': 'queue_paused'}
    assert api.put('/api/v1/admin/queue', headers=admin,
                   json={'name': 'match:scrimmage', 'paused': False, 'reason': 'xong'}).status_code == 200
    assert create(api, a, b).status_code == 202
