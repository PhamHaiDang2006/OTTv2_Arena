from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from freezegun import freeze_time
from sqlalchemy import func, select

from app import contract
from app.db import session_scope
from app.models import ActiveBot, CallbackReceipt, Game, Match, Outbox
from app.queue import get_redis
from app.scheduler import watchdog_once
from app.storage import get_storage
from tests.helpers import FakeWorker, job_for_game, make_admin, make_ready_submission, make_team, rq_job_ids, rq_payload


def scrimmage(api, team, opponent):
    response = api.post('/api/v1/scrimmages', headers=team.member, json={'opponent_team_id': str(opponent.id)})
    assert response.status_code == 202, response.text
    return response.json()['match_id']


def games_of(api, headers, match_id):
    return api.get(f'/api/v1/matches/{match_id}', headers=headers).json()['games']


def events(kind: str | None = None):
    with session_scope() as db:
        rows = [o.payload for o in db.scalars(select(Outbox).where(Outbox.kind == 'event').order_by(Outbox.id))]
    return [e for e in rows if kind is None or e['type'] == kind]


def relogin(team):
    """Mint fresh tokens under the current (possibly frozen) clock."""
    from tests.helpers import TeamCtx
    return TeamCtx(team.id, team.slug, team.captain_id, team.member_id)


def setup_pair():
    a, b = make_team('doi-a'), make_team('doi-b')
    sub_a, sub_b = make_ready_submission(a.id), make_ready_submission(b.id)
    return a, b, sub_a, sub_b


def test_scrimmage_creates_two_swapped_games_with_contract_jobs(api):
    a, b, sub_a, sub_b = setup_pair()
    match_id = scrimmage(api, a, b)
    match = api.get(f'/api/v1/matches/{match_id}', headers=a.member).json()
    assert match['stage'] == 'scrimmage' and match['best_of'] == 'two_games' and match['status'] == 'queued'
    g1, g2 = match['games']
    assert (g1['blue_submission_id'], g1['red_submission_id']) == (str(sub_a), str(sub_b))
    assert (g2['blue_submission_id'], g2['red_submission_id']) == (str(sub_b), str(sub_a))
    jobs = rq_job_ids('match:scrimmage')
    assert len(jobs) == 2 and rq_job_ids('match:tournament') == []
    for job_id in jobs:
        payload = rq_payload(job_id)
        assert not contract.errors('MatchJob', payload)
        assert payload['config']['players'] == payload['players']
        assert payload['config']['initial_fen'] == contract.INITIAL_FEN
    # Changing the active bot later does not change the games already created.
    newer = make_ready_submission(a.id)
    with session_scope() as db:
        assert db.get(ActiveBot, (a.id, 'scrimmage')).submission_id == newer
    assert games_of(api, a.member, match_id)[0]['blue_submission_id'] == str(sub_a)


def test_scrimmage_rules(api):
    a, b, _, _ = setup_pair()
    no_bot = make_team('nobot')
    self_play = api.post('/api/v1/scrimmages', headers=a.member, json={'opponent_team_id': str(a.id)})
    assert self_play.status_code == 409 and self_play.json()['error']['code'] == 'SELF_SCRIMMAGE'
    assert api.post('/api/v1/scrimmages', headers=a.member, json={'opponent_team_id': str(no_bot.id)}).status_code == 409
    assert api.post('/api/v1/scrimmages', headers=a.member,
                    json={'opponent_team_id': str(uuid.uuid4())}).status_code == 404
    own = api.post('/api/v1/scrimmages', headers=no_bot.member, json={'opponent_team_id': str(a.id)})
    assert own.status_code == 409 and own.json()['error']['code'] == 'SUBMISSION_NOT_READY'
    assert api.post('/api/v1/scrimmages', headers=make_admin(), json={'opponent_team_id': str(a.id)}).status_code == 403


def test_scrimmage_quota_resets_at_saigon_midnight(api):
    a, b, _, _ = setup_pair()
    # 23:30 Asia/Saigon on 2026-10-17 is 16:30Z; reset at 17:00Z.
    with freeze_time('2026-10-17T16:30:00Z'):
        a, b = relogin(a), relogin(b)
        quota = api.get('/api/v1/scrimmages/quota', headers=a.member).json()
        assert quota == {'limit': 60, 'used': 0, 'remaining': 60, 'resets_at': '2026-10-17T17:00:00.000Z'}
        with session_scope() as db:
            for _ in range(60):
                db.add(Match(stage='scrimmage', team_a_id=a.id, team_b_id=b.id, best_of='two_games', status='finished',
                             created_by_team_id=a.id, created_at=datetime.fromisoformat('2026-10-17T16:00:00+00:00')))
        exceeded = api.post('/api/v1/scrimmages', headers=a.member, json={'opponent_team_id': str(b.id)})
        assert exceeded.status_code == 429 and exceeded.json()['error']['code'] == 'QUOTA_EXCEEDED'
        # The opponent's quota is separate: matches count for the team that created them.
        assert api.get('/api/v1/scrimmages/quota', headers=b.member).json()['used'] == 0
    with freeze_time('2026-10-17T17:00:01Z'):
        a = relogin(a)
        assert api.get('/api/v1/scrimmages/quota', headers=a.member).json()['remaining'] == 60
        assert api.post('/api/v1/scrimmages', headers=a.member, json={'opponent_team_id': str(b.id)}).status_code == 202


def test_scrimmage_visibility(api):
    a, b, _, _ = setup_pair()
    outsider = make_team('doi-c')
    match_id = scrimmage(api, a, b)
    game_id = games_of(api, a.member, match_id)[0]['id']
    for path in (f'/api/v1/matches/{match_id}', f'/api/v1/games/{game_id}', f'/api/v1/games/{game_id}/replay'):
        assert api.get(path, headers=outsider.member).status_code == 404
    assert api.get('/api/v1/scrimmages', headers=outsider.member).json()['total'] == 0
    assert api.get('/api/v1/scrimmages', headers=b.member).json()['total'] == 1
    assert api.get('/api/v1/matches', headers=outsider.member).status_code == 422  # tournament_id is required
    assert api.get(f'/api/v1/matches/{match_id}', headers=make_admin()).status_code == 200
    assert api.get(f'/api/v1/games/{game_id}/replay', headers=a.member).status_code == 409


def test_finished_games_complete_match_once(api):
    a, b, _, _ = setup_pair()
    match_id = scrimmage(api, a, b)
    g1, g2 = (g['id'] for g in games_of(api, a.member, match_id))
    worker = FakeWorker(api)
    body, lease = worker.play(g1, winner='BLUE')
    match = api.get(f'/api/v1/matches/{match_id}', headers=a.member).json()
    assert match['status'] == 'running' and (match['score_a'], match['score_b']) == (1, 0)
    worker.play(g2, winner='BLUE')  # game 2: B is BLUE → 1–1 draw
    match = api.get(f'/api/v1/matches/{match_id}', headers=a.member).json()
    assert match['status'] == 'finished' and match['winner_team_id'] is None
    assert (match['score_a'], match['score_b']) == (1, 1)
    game = api.get(f'/api/v1/games/{g1}', headers=a.member).json()
    assert game['result'] == {'winner': 'BLUE', 'reason': 'GOAL', 'plies': 10} and game['replay_available'] is True
    # Duplicate terminal callback (same token, after lease release) is accepted without effects.
    before = len(events())
    assert worker.post_game(g1, body, lease).status_code == 200
    assert len(events()) == before
    finished = events('match.finished')
    assert len(finished) == 2 and {e['channel'] for e in finished} == {f'team:{a.id}', f'team:{b.id}'}
    assert len(events('game.finished')) == 4
    for event in events():
        assert not contract.errors('WsEvent', event)
    # Different terminal payload for the same job → 409; current result unchanged.
    assert worker.post_game(g1, {**body, 'result': {**body['result'], 'winner': 'RED'}}, lease).status_code == 409
    assert api.get(f'/api/v1/games/{g1}', headers=a.member).json()['result']['winner'] == 'BLUE'


def test_replay_url_and_canonical_artifacts(api):
    a, b, _, _ = setup_pair()
    match_id = scrimmage(api, a, b)
    g1 = games_of(api, a.member, match_id)[0]['id']
    FakeWorker(api).play(g1)
    signed = api.get(f'/api/v1/games/{g1}/replay', headers=b.member).json()
    assert f'replays/{g1}.json.gz' in signed['url'] and signed['expires_at'].endswith('Z')
    assert get_storage().head(f'replays/{g1}.json.gz') is not None
    admin = make_admin()
    logs = api.get(f'/api/v1/admin/games/{g1}/logs', headers=admin).json()
    assert logs['BLUE'] == 'blue stderr\n' and logs['RED'] == 'red stderr\n'
    assert api.get(f'/api/v1/admin/games/{g1}/logs', headers=a.member).status_code == 403


def test_callback_validation_and_stale_lease(api):
    a, b, _, _ = setup_pair()
    match_id = scrimmage(api, a, b)
    g1 = games_of(api, a.member, match_id)[0]['id']
    job = job_for_game(g1)
    worker = FakeWorker(api)
    lease = worker.claim(job.id)
    running = worker.game_payload(job, 'running')
    assert worker.post_game(g1, {**running, 'attempt': 2}, lease).status_code == 409
    assert worker.post_game(g1, running, str(uuid.uuid4())).status_code == 409  # not the lease owner
    assert worker.post_game(str(uuid.uuid4()), running, lease).status_code == 422  # URL id ≠ payload id
    assert worker.post_game(g1, {**running, 'duration_ms': 5}, lease).status_code == 422  # schema: running → 0
    finished = worker.game_payload(job, 'finished', lease=lease)
    missing = {**finished, 'replay_key': f'staging/{job.id}/nothing.json.gz'}
    response = worker.post_game(g1, missing, lease)
    assert response.status_code == 422 and response.json()['error']['details']['reason'] == 'artifact_missing'
    assert worker.post_game(g1, running, lease).status_code == 200
    assert worker.post_game(g1, finished, lease).status_code == 200
    # Late `running` after terminal: 409, no state regression.
    get_redis().delete(f'ottv2:lease:{job.id}')
    assert worker.post_game(g1, running, lease).status_code == 409
    assert api.get(f'/api/v1/games/{g1}', headers=a.member).json()['status'] == 'finished'


def test_infra_error_creates_new_attempt_up_to_four_then_blocks(api):
    a, b, _, _ = setup_pair()
    match_id = scrimmage(api, a, b)
    g1 = games_of(api, a.member, match_id)[0]['id']
    worker = FakeWorker(api)
    current = g1
    seen = [g1]
    for attempt in range(1, 5):
        job = job_for_game(current)
        assert job.attempt == attempt
        worker.infra(current)
        games = [g for g in games_of(api, a.member, match_id) if g['game_index'] == 1]
        assert len(games) == attempt + (1 if attempt < 4 else 0)
        latest = max(games, key=lambda g: g['attempt'])
        if attempt < 4:
            assert latest['is_current'] and latest['status'] == 'queued' and latest['id'] not in seen
            assert sum(g['is_current'] for g in games) == 1
            # Same seed, sides and submissions; new job id.
            assert job_for_game(latest['id']).payload['config']['seed'] == job.payload['config']['seed']
            current = latest['id']
            seen.append(current)
    match = api.get(f'/api/v1/matches/{match_id}', headers=a.member).json()
    assert match['status'] == 'blocked'
    old = api.get(f'/api/v1/games/{g1}', headers=a.member).json()
    assert old['status'] == 'infra_error' and old['is_current'] is False and old['result'] is None


def test_old_attempt_callback_does_not_replace_current(api):
    a, b, _, _ = setup_pair()
    match_id = scrimmage(api, a, b)
    g1 = games_of(api, a.member, match_id)[0]['id']
    worker = FakeWorker(api)
    old_job = job_for_game(g1)
    old_lease = worker.claim(old_job.id)
    worker.post_game(g1, worker.game_payload(old_job, 'running'), old_lease)
    # The lease expires; the watchdog declares the attempt lost and creates attempt 2.
    worker.release(old_job.id)
    assert watchdog_once() == 1
    current = next(g for g in games_of(api, a.member, match_id) if g['game_index'] == 1 and g['is_current'])
    assert current['attempt'] == 2
    # The stale worker comes back with a finished result for attempt 1: rejected, nothing counted.
    late = worker.game_payload(old_job, 'finished', lease=old_lease)
    assert worker.post_game(g1, late, old_lease).status_code == 409
    match = api.get(f'/api/v1/matches/{match_id}', headers=a.member).json()
    assert (match['score_a'], match['score_b']) == (0, 0)


def test_watchdog_ignores_unclaimed_and_live_jobs(api):
    a, b, _, _ = setup_pair()
    match_id = scrimmage(api, a, b)
    g1, g2 = (g['id'] for g in games_of(api, a.member, match_id))
    worker = FakeWorker(api)
    worker.claim(job_for_game(g1).id)
    assert watchdog_once() == 0  # g1 leased, g2 never claimed
    statuses = {g['id']: g['status'] for g in games_of(api, a.member, match_id)}
    assert statuses == {g1: 'queued', g2: 'queued'}
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(Game)) == 2


def test_watchdog_build_lease_lost_fails_submission(api):
    from tests.helpers import PY_BOT, open_jobs, upload, zip_bytes
    team = make_team('doi-a')
    submission_id = upload(api, team.member, zip_bytes(PY_BOT)).json()['id']
    job = open_jobs('build')[0]
    worker = FakeWorker(api)
    lease = worker.claim(job.id)
    worker.build(job, status='building', lease=lease)
    worker.release(job.id)
    assert watchdog_once() == 1
    detail = api.get(f'/api/v1/submissions/{submission_id}', headers=team.member).json()
    assert detail['status'] == 'failed' and detail['build_error']['code'] == 'INFRA_ERROR'


def test_receipts_store_lease_token(api):
    a, b, _, _ = setup_pair()
    match_id = scrimmage(api, a, b)
    g1 = games_of(api, a.member, match_id)[0]['id']
    _, lease = FakeWorker(api).play(g1)
    with session_scope() as db:
        receipt = db.scalar(select(CallbackReceipt))
        assert str(receipt.lease_token) == lease and receipt.status == 'finished'


def test_heartbeat_and_queue_view(api):
    admin = make_admin()
    worker_headers = {'Authorization': 'Bearer test-worker-token'}
    body = {'worker_id': 'match-1', 'kind': 'match', 'job_id': None, 'sent_at': '2026-10-17T00:00:00Z'}
    assert api.post('/api/v1/internal/workers/heartbeat', json=body, headers=worker_headers, idem=False).status_code == 200
    assert api.post('/api/v1/internal/workers/heartbeat', json=body, headers=admin, idem=False).status_code == 401
    queue = api.get('/api/v1/admin/queue', headers=admin).json()
    assert [q['name'] for q in queue['queues']] == ['build', 'match:scrimmage', 'match:tournament']
    assert queue['workers'][0]['id'] == 'match-1' and queue['workers'][0]['status'] == 'idle'
    with freeze_time(datetime.now(UTC) + timedelta(seconds=120)):
        assert api.get('/api/v1/admin/queue', headers=admin).json()['workers'][0]['status'] == 'offline'
