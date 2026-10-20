"""8-team development tournament driven entirely through the HTTP API and the worker callback contract:
draw → lock → group round → knockout → final, plus freeze snapshots, rerun/override and downstream locks."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.db import session_scope
from app.models import AuditLog, FrozenBot, MatchOverride, WorkerJob
from tests.helpers import FakeWorker, make_admin, make_ready_submission, make_team

ADMIN = '/api/v1/admin'


def reason(text: str = 'vận hành thử') -> dict:
    return {'reason': text}


class Tournament:
    def __init__(self, api, teams: int = 8):
        self.api = api
        self.admin = make_admin()
        self.teams = [make_team(f'team-{i}', seed=i) for i in range(1, teams + 1)]
        self.bots = {t.id: make_ready_submission(t.id, active=('scrimmage', 'tournament')) for t in self.teams}
        self.seed_of = {str(t.id): i for i, t in enumerate(self.teams, start=1)}
        response = api.post(f'{ADMIN}/tournaments', headers=self.admin,
                            json={'name': 'Giải thử', 'engine_version': '1.0.0', 'ruleset_id': 'dev-v1'})
        assert response.status_code == 201, response.text
        self.id = response.json()['id']
        self.rounds = {}

    def post(self, path, body, **kw):
        return self.api.post(f'{ADMIN}{path}', headers=self.admin, json=body, **kw)

    def create_rounds(self):
        for stage in ('group', 'quarterfinal', 'semifinal', 'third_place', 'final'):
            response = self.post(f'/tournaments/{self.id}/rounds', {'stage': stage, 'freeze_at': None})
            assert response.status_code == 201, response.text
            self.rounds[stage] = response.json()['id']

    def freeze(self, stage):
        response = self.post(f'/rounds/{self.rounds[stage]}/freeze', reason())
        assert response.status_code == 200, response.text
        return response.json()

    def run(self, stage, key=True):
        response = self.post(f'/rounds/{self.rounds[stage]}/run', reason(), idem=key)
        assert response.status_code == 202, response.text
        return response.json()

    def round(self, stage):
        rounds = self.api.get(f'/api/v1/tournaments/{self.id}/rounds').json()['items']
        return next(r for r in rounds if r['stage'] == stage)

    def matches(self, stage=None):
        query = f'?round_id={self.rounds[stage]}&page_size=100' if stage else '?page_size=100'
        return self.api.get(f'{ADMIN}/matches{query}', headers=self.admin).json()['items']

    def bracket(self):
        return self.api.get(f'/api/v1/bracket?tournament_id={self.id}').json()['items']


def stronger_wins(job: WorkerJob, seed_of) -> str:
    blue = seed_of_team(job.payload['players']['BLUE']['team'])
    red = seed_of_team(job.payload['players']['RED']['team'])
    return 'BLUE' if blue < red else 'RED'


def seed_of_team(slug: str) -> int:
    return int(slug.rsplit('-', 1)[1])


def play_all(api, policy=None) -> int:
    """Play every open match job until none remain (knockout games appear as earlier ones finish)."""
    worker = FakeWorker(api)
    played = 0
    while True:
        with session_scope() as db:
            jobs = list(db.scalars(select(WorkerJob).where(WorkerJob.kind == 'match', WorkerJob.status != 'terminal')
                                   .order_by(WorkerJob.created_at)))
        if not jobs:
            return played
        for job in jobs:
            winner = (policy or stronger_wins)(job, None)
            worker.play(job.game_id, winner=winner, plies=20 + played)
            played += 1


def test_full_development_tournament(api):
    t = Tournament(api)
    # Draw: may be redrawn until locked; the seed is audited before the groups.
    first = t.post(f'/tournaments/{t.id}/draw', reason('bốc thăm'))
    assert first.status_code == 200, first.text
    draw = first.json()
    assert [g['label'] for g in draw['groups']] == ['A', 'B', 'C', 'D']
    pots = [[t.seed_of[x] for x in g['team_ids']] for g in draw['groups']]
    assert sorted(p[0] for p in pots) == [1, 2, 3, 4] and sorted(p[1] for p in pots) == [5, 6, 7, 8]
    from app.tournament.draw import draw_groups
    expected = draw_groups(list(range(1, 9)), draw['draw_seed'])
    assert {g['label']: [t.seed_of[x] for x in g['team_ids']] for g in draw['groups']} == expected
    assert t.post(f'/tournaments/{t.id}/draw', reason('bốc lại')).status_code == 200
    locked = t.post(f'/tournaments/{t.id}/draw/lock', reason('chốt'))
    assert locked.status_code == 200 and locked.json()['locked'] is True
    assert t.post(f'/tournaments/{t.id}/draw', reason('sau chốt')).status_code == 409
    assert t.post(f'/tournaments/{t.id}/draw/lock', reason('lần 2')).status_code == 409
    draw = api.get(f'{ADMIN}/tournaments/{t.id}/draw', headers=t.admin).json()
    with session_scope() as db:
        audits = [a.action for a in db.scalars(select(AuditLog).where(AuditLog.target_id == uuid.UUID(t.id))
                                               .order_by(AuditLog.created_at))]
    assert audits[:3] == ['tournament.create', 'tournament.draw_seed', 'tournament.draw']

    t.create_rounds()
    assert t.post(f'/tournaments/{t.id}/rounds', {'stage': 'group', 'freeze_at': None}).status_code == 409
    run_early = t.post(f'/rounds/{t.rounds["group"]}/run', reason())
    assert run_early.status_code == 409 and run_early.json()['error']['code'] == 'ROUND_NOT_FROZEN'
    assert t.post(f'/rounds/{t.rounds["quarterfinal"]}/freeze', reason()).status_code == 409  # group not finished

    # Freeze: snapshot of tournament bots, immutable afterwards.
    snapshot = t.freeze('group')
    assert {b['submission_id'] for b in snapshot['bots']} == {str(s) for s in t.bots.values()}
    newer = make_ready_submission(t.teams[0].id, active=('tournament',))
    assert api.get(f'{ADMIN}/rounds/{t.rounds["group"]}/snapshot', headers=t.admin).json() == snapshot
    assert t.post(f'/rounds/{t.rounds["group"]}/freeze', reason()).status_code == 409
    assert api.patch(f'{ADMIN}/rounds/{t.rounds["group"]}', headers=t.admin,
                     json={'freeze_at': None, 'reason': 'x'}).status_code == 409

    # Run with the same key twice → one set of matches.
    key = str(uuid.uuid4())
    run = t.run('group', key)
    assert t.run('group', key) == run
    assert len(run['match_ids']) == 4
    assert t.post(f'/rounds/{t.rounds["group"]}/run', reason()).status_code == 409
    group_matches = t.matches('group')
    assert len(group_matches) == 4 and all(m['best_of'] == 'two_games' for m in group_matches)
    used = {g[k] for m in group_matches for g in m['games'] for k in ('blue_submission_id', 'red_submission_id')}
    assert str(newer) not in used and used == {str(s) for s in t.bots.values()}
    assert api.get(f'/api/v1/tournaments/{t.id}').json()['status'] == 'running'

    assert play_all(api) == 8
    assert t.round('group')['status'] == 'finished'
    standings = api.get(f'/api/v1/standings?tournament_id={t.id}').json()['items']
    assert len(standings) == 8 and [s['rank'] for s in standings] == [1, 2] * 4
    winners = {s['team']['slug'] for s in standings if s['rank'] == 1}
    assert winners == {'team-1', 'team-2', 'team-3', 'team-4'}
    qf_slots = [s for s in t.bracket() if s['round'] == 'quarterfinal']
    assert [s['source_rule'] for s in qf_slots] == ['A1', 'B2', 'B1', 'A2', 'C1', 'D2', 'D1', 'C2']
    assert all(s['team'] is not None for s in qf_slots)

    # Rerun a group game while the next round is still draft: allowed, round reopens, standings recomputed.
    target = group_matches[0]['games'][0]
    rerun = t.post(f'/games/{target["id"]}/rerun', reason('chạy lại thử'))
    assert rerun.status_code == 202, rerun.text
    assert rerun.json()['previous_game_id'] == target['id'] and rerun.json()['attempt'] == 2
    assert t.round('group')['status'] == 'running'
    assert all(s['team'] is None for s in t.bracket() if s['round'] == 'quarterfinal')
    match = api.get(f'/api/v1/matches/{group_matches[0]["id"]}', headers=t.admin).json()
    attempts = [(g['attempt'], g['is_current'], g['status']) for g in match['games'] if g['game_index'] == 1]
    assert attempts == [(1, False, 'finished'), (2, True, 'queued')]
    assert match['status'] == 'running'
    assert play_all(api) == 1
    assert t.round('group')['status'] == 'finished'

    # Quarterfinals: first_to_2; the next game is created only while undecided.
    t.freeze('quarterfinal')
    rerun_locked = t.post(f'/games/{target["id"]}/rerun', reason())
    assert rerun_locked.status_code == 409  # not current any more
    current = next(g for g in api.get(f'/api/v1/matches/{group_matches[0]["id"]}', headers=t.admin).json()['games']
                   if g['is_current'] and g['game_index'] == 1)
    blocked = t.post(f'/games/{current["id"]}/rerun', reason())
    assert blocked.status_code == 409 and blocked.json()['error']['code'] == 'DOWNSTREAM_STARTED'
    override_locked = t.post(f'/matches/{group_matches[0]["id"]}/override',
                             {'winner_team_id': None, 'score_a': 1, 'score_b': 1, 'reason': 'x'})
    assert override_locked.json()['error']['code'] == 'DOWNSTREAM_STARTED'
    qf = t.run('quarterfinal')
    assert len(qf['match_ids']) == 4
    qf_matches = t.matches('quarterfinal')
    assert all(len(m['games']) == 1 and m['best_of'] == 'first_to_2' for m in qf_matches)

    # QF: the weaker seed wins game 1, then the stronger seed wins → 3 games; game 3 BLUE = stronger seed.
    def upset_first(job, _):
        stronger = stronger_wins(job, None)
        return ('RED' if stronger == 'BLUE' else 'BLUE') if game_index_of(job) == 1 else stronger
    assert play_all(api, upset_first) == 12
    # The QF snapshot is taken at QF freeze, so team-1 now plays with its newer tournament bot.
    qf_snapshot = api.get(f'{ADMIN}/rounds/{t.rounds["quarterfinal"]}/snapshot', headers=t.admin).json()
    team_of_bot = {b['submission_id']: b['team_id'] for b in qf_snapshot['bots']}
    assert str(newer) in team_of_bot
    for m in t.matches('quarterfinal'):
        assert m['status'] == 'finished' and len(m['games']) == 3
        a_seed, b_seed = (seed_of_team(m[k]['slug']) for k in ('team_a', 'team_b'))
        stronger = m['team_a']['id'] if a_seed < b_seed else m['team_b']['id']
        assert m['winner_team_id'] == stronger and sorted((m['score_a'], m['score_b'])) == [1, 2]
        sides = [g['blue_submission_id'] for g in sorted(m['games'], key=lambda g: g['game_index'])]
        assert [team_of_bot[s] for s in sides] == [m['team_a']['id'], m['team_b']['id'], stronger]
    assert t.round('quarterfinal')['status'] == 'finished'
    sf_slots = [s for s in t.bracket() if s['round'] == 'semifinal']
    assert all(s['team'] for s in sf_slots)

    # Override a QF result before the semifinal is frozen: audited, bracket follows the override.
    qf1 = next(m for m in t.matches('quarterfinal') if m['id'] == next(
        s['match_id'] for s in t.bracket() if s['round'] == 'quarterfinal' and s['slot_index'] == 1))
    loser = qf1['team_b']['id'] if qf1['winner_team_id'] == qf1['team_a']['id'] else qf1['team_a']['id']
    bad = t.post(f'/matches/{qf1["id"]}/override', {'winner_team_id': loser, 'score_a': 1, 'score_b': 1, 'reason': 'x'})
    assert bad.status_code == 422
    scores = (2, 0) if loser == qf1['team_a']['id'] else (0, 2)
    override = t.post(f'/matches/{qf1["id"]}/override', {'winner_team_id': loser, 'score_a': scores[0],
                                                          'score_b': scores[1], 'reason': 'Xử thua do vi phạm'})
    assert override.status_code == 200, override.text
    assert override.json()['winner_team_id'] == loser
    assert next(s for s in t.bracket() if s['source_rule'] == 'W:QF1')['team']['id'] == loser
    with session_scope() as db:
        row = db.scalar(select(MatchOverride))
        assert row.reason == 'Xử thua do vi phạm' and row.before['winner_team_id'] != row.after['winner_team_id']
    log = api.get(f'{ADMIN}/audit-log?action=match.override', headers=t.admin).json()['items']
    assert len(log) == 1 and log[0]['payload']['reason'] == 'Xử thua do vi phạm'

    for stage in ('semifinal',):
        t.freeze(stage)
        t.run(stage)
    play_all(api)
    assert t.round('semifinal')['status'] == 'finished'
    assert all(s['team'] for s in t.bracket() if s['round'] in ('final', 'third_place'))
    for stage in ('third_place', 'final'):
        t.freeze(stage)
        t.run(stage)
    final_matches = t.matches('final')
    assert final_matches[0]['best_of'] == 'first_to_3'
    play_all(api)
    tournament = api.get(f'/api/v1/tournaments/{t.id}').json()
    assert tournament['status'] == 'finished'
    final = t.matches('final')[0]
    assert final['status'] == 'finished' and max(final['score_a'], final['score_b']) == 3
    after = t.post(f'/matches/{final["id"]}/override', {'winner_team_id': final['team_a']['id'], 'score_a': 3,
                                                         'score_b': 0, 'reason': 'x'})
    assert after.status_code == 409 and after.json()['error']['code'] == 'DOWNSTREAM_STARTED'
    # Every admin mutation left an audit row; rejected ones too.
    actions = {a['action'] for a in api.get(f'{ADMIN}/audit-log?page_size=100', headers=t.admin).json()['items']}
    assert {'round.freeze', 'round.run', 'game.rerun', 'match.override', 'tournament.finished'} <= actions
    rejected = api.get(f'{ADMIN}/audit-log?action=adminOverrideMatch.rejected', headers=t.admin).json()
    assert rejected['total'] >= 1


def game_index_of(job: WorkerJob) -> int:
    from app.models import Game
    with session_scope() as db:
        return db.get(Game, job.game_id).game_index


def test_freeze_requires_ready_tournament_bots(api):
    t = Tournament(api)
    t.post(f'/tournaments/{t.id}/draw', reason())
    t.create_rounds()
    early = t.post(f'/rounds/{t.rounds["group"]}/freeze', reason())
    assert early.status_code == 409 and early.json()['error']['details']['reason'] == 'draw_not_locked'
    t.post(f'/tournaments/{t.id}/draw/lock', reason())
    with session_scope() as db:
        from app.models import ActiveBot
        db.delete(db.get(ActiveBot, (t.teams[3].id, 'tournament')))
    missing = t.post(f'/rounds/{t.rounds["group"]}/freeze', reason())
    assert missing.status_code == 409 and missing.json()['error']['code'] == 'SUBMISSION_NOT_READY'
    assert missing.json()['error']['details']['team_ids'] == [str(t.teams[3].id)]
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(FrozenBot)) == 0


def test_draw_requires_valid_team_set(api):
    admin = make_admin()
    for i in range(1, 8):
        make_team(f'team-{i}', seed=i)
    tid = api.post(f'{ADMIN}/tournaments', headers=admin,
                   json={'name': 'T', 'engine_version': '1.0.0', 'ruleset_id': 'dev-v1'}).json()['id']
    response = api.post(f'{ADMIN}/tournaments/{tid}/draw', headers=admin, json=reason())
    assert response.status_code == 409 and response.json()['error']['details']['team_count'] == 7
    make_team('team-9', seed=9)
    response = api.post(f'{ADMIN}/tournaments/{tid}/draw', headers=admin, json=reason())
    assert response.json()['error']['details']['reason'] == 'invalid_seeds'


def test_development_ruleset_blocks_tournaments_without_flag(api):
    from app.config import get_settings
    admin = make_admin()
    get_settings().allow_development_tournaments = False
    response = api.post(f'{ADMIN}/tournaments', headers=admin,
                        json={'name': 'T', 'engine_version': '1.0.0', 'ruleset_id': 'dev-v1'})
    assert response.status_code == 409 and response.json()['error']['code'] == 'RULESET_UNCONFIRMED'


def test_freeze_rejects_bot_built_for_another_engine(api):
    from app.models import Submission
    t = Tournament(api)
    t.post(f'/tournaments/{t.id}/draw', reason())
    t.post(f'/tournaments/{t.id}/draw/lock', reason())
    t.create_rounds()
    with session_scope() as db:
        db.get(Submission, t.bots[t.teams[0].id]).engine_version = '0.9.0'
    response = t.post(f'/rounds/{t.rounds["group"]}/freeze', reason())
    assert response.status_code == 409 and response.json()['error']['code'] == 'SUBMISSION_NOT_READY'
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(FrozenBot)) == 0


def test_scheduled_freeze_uses_same_code_path(api):
    from datetime import UTC, datetime, timedelta

    from app.scheduler import scheduled_freeze_once
    t = Tournament(api)
    t.post(f'/tournaments/{t.id}/draw', reason())
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat().replace('+00:00', 'Z')
    rid = t.post(f'/tournaments/{t.id}/rounds', {'stage': 'group', 'freeze_at': past}).json()['id']
    assert scheduled_freeze_once() == 0  # draw not locked → rejected once, audited once
    assert scheduled_freeze_once() == 0
    rejected = api.get(f'{ADMIN}/audit-log?action=round.freeze.rejected', headers=t.admin).json()
    assert rejected['total'] == 1 and rejected['items'][0]['actor_user_id'] is None
    t.post(f'/tournaments/{t.id}/draw/lock', reason())
    assert scheduled_freeze_once() == 1
    assert api.get(f'{ADMIN}/rounds/{rid}/snapshot', headers=t.admin).status_code == 200
    log = api.get(f'{ADMIN}/audit-log?action=round.freeze', headers=t.admin).json()['items']
    assert log[0]['actor_user_id'] is None and log[0]['payload']['scheduled'] is True


def test_blocked_match_continues_after_admin_rerun(api):
    t = Tournament(api)
    t.post(f'/tournaments/{t.id}/draw', reason())
    t.post(f'/tournaments/{t.id}/draw/lock', reason())
    t.create_rounds()
    t.freeze('group')
    t.run('group')
    match = t.matches('group')[0]
    game_id = match['games'][0]['id']
    worker = FakeWorker(api)
    for _ in range(4):
        worker.infra(game_id)
        current = [g for g in api.get(f'/api/v1/matches/{match["id"]}', headers=t.admin).json()['games']
                   if g['game_index'] == 1 and g['is_current']][0]
        game_id = current['id']
    detail = api.get(f'/api/v1/matches/{match["id"]}', headers=t.admin).json()
    assert detail['status'] == 'blocked'
    rerun = t.post(f'/games/{game_id}/rerun', reason('hạ tầng đã ổn'))
    assert rerun.status_code == 202 and rerun.json()['attempt'] == 5
    worker.play(rerun.json()['game_id'])
    assert api.get(f'/api/v1/matches/{match["id"]}', headers=t.admin).json()['status'] in ('running', 'finished')
