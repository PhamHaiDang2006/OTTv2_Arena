"""Tournament operations: draw, rounds, freeze/snapshot, run, bracket, rerun/override with downstream locks.

State machines (contracts/behavior.md): tournament draft → drawn → running → finished; round draft → frozen →
running → finished. A frozen round is the boundary that locks the previous round's results.

Row-lock order everywhere (prevents deadlocks between callbacks, the watchdog and admin actions):
worker_job → match → game → tournament → round → group.
"""
from __future__ import annotations

import uuid
from itertools import combinations
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.audit import audit
from app.errors import ApiError, conflict, invalid, not_found
from app.matches import service as matches
from app.models import (
    ActiveBot,
    BracketSlot,
    FrozenBot,
    Game,
    Group,
    GroupTeam,
    Match,
    MatchOverride,
    Round,
    RoundSnapshot,
    Submission,
    Team,
    Tournament,
)
from app.public.router import tournament_enabled
from app.serializers import s
from app.timeutil import utcnow
from app.tournament import standings
from app.tournament.draw import ALGORITHM, LABELS, draw_groups, new_seed

TEAM_COUNTS = (20, 8)  # dev-v1 TOUR-01: 20-team format, 8-team development format
PREVIOUS = {'group': None, 'quarterfinal': 'group', 'semifinal': 'quarterfinal', 'third_place': 'semifinal',
            'final': 'semifinal'}
NEXT = {'group': ('quarterfinal',), 'quarterfinal': ('semifinal',), 'semifinal': ('third_place', 'final'),
        'third_place': (), 'final': ()}
STAGE_ORDER = {'group': 0, 'quarterfinal': 1, 'semifinal': 2, 'third_place': 3, 'final': 4}
SLOT_RULES = {
    'quarterfinal': ('A1', 'B2', 'B1', 'A2', 'C1', 'D2', 'D1', 'C2'),
    'semifinal': ('W:QF1', 'W:QF2', 'W:QF3', 'W:QF4'),
    'third_place': ('L:SF1', 'L:SF2'),
    'final': ('W:SF1', 'W:SF2'),
}
CODE_PREFIX = {'quarterfinal': 'QF', 'semifinal': 'SF', 'third_place': 'TP', 'final': 'F'}


def require_enabled() -> None:
    if not tournament_enabled():
        raise conflict('RULESET_UNCONFIRMED', ruleset_id='dev-v1', ruleset_status='development')


def get_tournament(db: Session, tournament_id: uuid.UUID, lock: bool = False) -> Tournament:
    row = db.get(Tournament, tournament_id, with_for_update=lock)
    if row is None:
        raise not_found('Không tìm thấy giải')
    return row


def get_round(db: Session, round_id: uuid.UUID, lock: bool = False) -> Round:
    row = db.get(Round, round_id, with_for_update=lock)
    if row is None:
        raise not_found('Không tìm thấy vòng đấu')
    return row


def lock_round(db: Session, round_id: uuid.UUID) -> Round:
    """Lock the tournament, then the round (see the lock order in the module docstring)."""
    row = get_round(db, round_id)
    get_tournament(db, row.tournament_id, lock=True)
    db.refresh(row, with_for_update=True)
    return row


def lock_scope(db: Session, model, row_id: uuid.UUID) -> None:
    db.execute(select(model.id).where(model.id == row_id).with_for_update())


def stage_round(db: Session, tournament_id: uuid.UUID, stage: str | None) -> Round | None:
    if stage is None:
        return None
    return db.scalar(select(Round).where(Round.tournament_id == tournament_id, Round.stage == stage))


# --- tournament and draw -------------------------------------------------------------------------------------

def create_tournament(db: Session, actor_id: uuid.UUID, body: dict[str, Any]) -> Tournament:
    require_enabled()
    row = Tournament(name=body['name'], engine_version=body['engine_version'], ruleset_id=body['ruleset_id'],
                     status='draft')
    db.add(row)
    db.flush()
    for stage, rules in SLOT_RULES.items():
        for index, rule in enumerate(rules, start=1):
            db.add(BracketSlot(tournament_id=row.id, round=stage, slot_index=index, source_rule=rule))
    audit(db, actor_id, 'tournament.create', 'tournament', row.id, body)
    db.flush()
    return row


def groups_of(db: Session, tournament_id: uuid.UUID) -> list[Group]:
    return list(db.scalars(select(Group).where(Group.tournament_id == tournament_id).order_by(Group.label)))


def draw_body(db: Session, tournament: Tournament) -> dict[str, Any]:
    if tournament.draw_seed is None:
        raise not_found('Giải chưa bốc thăm')
    groups = []
    for group in groups_of(db, tournament.id):
        team_ids = db.scalars(select(GroupTeam.team_id).where(GroupTeam.group_id == group.id).order_by(GroupTeam.pot))
        groups.append({'id': s(group.id), 'label': group.label, 'team_ids': [s(t) for t in team_ids]})
    return {'tournament_id': s(tournament.id), 'draw_seed': tournament.draw_seed, 'locked': tournament.draw_locked,
            'groups': groups}


def _any_round_started(db: Session, tournament_id: uuid.UUID) -> bool:
    return db.scalar(select(Round.id).where(Round.tournament_id == tournament_id, Round.status != 'draft')
                     .limit(1)) is not None


def draw(db: Session, actor_id: uuid.UUID, tournament: Tournament, reason: str) -> dict[str, Any]:
    require_enabled()
    if tournament.status not in ('draft', 'drawn') or tournament.draw_locked:
        raise conflict(message='Chỉ bốc thăm lại khi kết quả chưa được chốt', reason='draw_locked')
    if _any_round_started(db, tournament.id):
        raise conflict(message='Đã có vòng đấu bị đóng băng', reason='round_frozen')
    teams = list(db.scalars(select(Team).where(Team.status == 'approved').order_by(Team.seed)))
    if len(teams) not in TEAM_COUNTS:
        raise conflict(message='Số đội đã duyệt phải là 20 (hoặc 8 khi phát triển)', reason='team_count',
                       team_count=len(teams))
    seeds = [t.seed for t in teams]
    if any(x is None for x in seeds) or sorted(seeds) != list(range(1, len(teams) + 1)):
        raise conflict(message='Hạt giống phải duy nhất và liên tục từ 1 đến N', reason='invalid_seeds')
    seed = new_seed()
    # The seed is written to audit_log before groups are computed.
    audit(db, actor_id, 'tournament.draw_seed', 'tournament', tournament.id,
          {'seed': seed, 'algorithm': ALGORITHM, 'team_count': len(teams), 'reason': reason})
    db.flush()
    by_seed = {t.seed: t for t in teams}
    result = draw_groups(seeds, seed)
    db.execute(delete(Group).where(Group.tournament_id == tournament.id))
    db.flush()
    created = []
    for label in LABELS:
        group = Group(tournament_id=tournament.id, label=label)
        db.add(group)
        db.flush()
        for pot, team_seed in enumerate(result[label]):
            db.add(GroupTeam(group_id=group.id, team_id=by_seed[team_seed].id, pot=pot))
        created.append(group)
    db.flush()
    tournament.draw_seed, tournament.status = seed, 'drawn'
    for group in created:
        standings.recompute_group(db, group, emit=False)
    body = draw_body(db, tournament)
    audit(db, actor_id, 'tournament.draw', 'tournament', tournament.id, {'reason': reason, **body})
    return body


def lock_draw(db: Session, actor_id: uuid.UUID, tournament: Tournament, reason: str) -> dict[str, Any]:
    require_enabled()
    if tournament.draw_seed is None or tournament.status != 'drawn':
        raise conflict(message='Giải chưa bốc thăm', reason='not_drawn')
    if tournament.draw_locked:
        raise conflict(message='Kết quả bốc thăm đã được chốt', reason='already_locked')
    tournament.draw_locked = True
    audit(db, actor_id, 'tournament.draw_lock', 'tournament', tournament.id, {'reason': reason})
    db.flush()
    return draw_body(db, tournament)


# --- rounds ---------------------------------------------------------------------------------------------------

def create_round(db: Session, actor_id: uuid.UUID, tournament: Tournament, stage: str, freeze_at) -> Round:
    require_enabled()
    if tournament.status == 'finished':
        raise conflict(message='Giải đã kết thúc', reason='tournament_finished')
    if stage_round(db, tournament.id, stage) is not None:
        raise conflict(message='Vòng này đã tồn tại', reason='duplicate_stage', stage=stage)
    row = Round(tournament_id=tournament.id, stage=stage, status='draft', freeze_at=freeze_at)
    db.add(row)
    db.flush()
    audit(db, actor_id, 'round.create', 'round', row.id, {'stage': stage, 'freeze_at': freeze_at})
    return row


def update_round(db: Session, actor_id: uuid.UUID, row: Round, freeze_at, reason: str) -> Round:
    require_enabled()
    if row.status != 'draft':
        raise conflict(message='Chỉ đổi giờ đóng băng khi vòng còn nháp', round_status=row.status)
    before = row.freeze_at
    row.freeze_at, row.freeze_failure_logged_for = freeze_at, None
    audit(db, actor_id, 'round.update', 'round', row.id, {'reason': reason, 'before': {'freeze_at': before},
                                                          'after': {'freeze_at': freeze_at}})
    db.flush()
    return row


def _previous_finished(db: Session, row: Round) -> bool:
    previous = stage_round(db, row.tournament_id, PREVIOUS[row.stage])
    return PREVIOUS[row.stage] is None or (previous is not None and previous.status == 'finished')


def participants(db: Session, row: Round) -> list[uuid.UUID]:
    if row.stage == 'group':
        return list(db.scalars(
            select(GroupTeam.team_id).join(Group, Group.id == GroupTeam.group_id).join(Team, Team.id == GroupTeam.team_id)
            .where(Group.tournament_id == row.tournament_id, Team.status != 'disqualified')
            .order_by(Group.label, GroupTeam.pot)))
    slots = list(db.scalars(select(BracketSlot).where(BracketSlot.tournament_id == row.tournament_id,
                                                      BracketSlot.round == row.stage).order_by(BracketSlot.slot_index)))
    if any(slot.team_id is None for slot in slots):
        raise conflict(message='Nhánh đấu của vòng này chưa đủ đội', reason='bracket_incomplete')
    return [slot.team_id for slot in slots]


def freeze_round(db: Session, actor_id: uuid.UUID | None, row: Round, reason: str | None,
                 scheduled: bool = False) -> RoundSnapshot:
    """Same code path for admin and scheduled freeze (actor None)."""
    require_enabled()
    tournament = get_tournament(db, row.tournament_id, lock=True)
    if row.status != 'draft':
        raise conflict(message='Vòng đã được đóng băng', round_status=row.status)
    if not tournament.draw_locked:
        raise conflict(message='Cần chốt kết quả bốc thăm trước khi đóng băng', reason='draw_not_locked')
    if not _previous_finished(db, row):
        raise conflict(message='Vòng trước chưa hoàn tất', reason='previous_round_not_finished')
    teams = participants(db, row)
    bots = dict(db.execute(
        select(ActiveBot.team_id, Submission.id).join(Submission, Submission.id == ActiveBot.submission_id)
        .where(ActiveBot.team_id.in_(teams), ActiveBot.scope == 'tournament', Submission.status == 'ready',
               Submission.engine_version == tournament.engine_version)).all())
    missing = [t for t in teams if t not in bots]
    if missing:
        raise conflict('SUBMISSION_NOT_READY', 'Có đội chưa có bot thi đấu sẵn sàng', team_ids=[s(t) for t in missing])
    now = utcnow()
    snapshot = RoundSnapshot(round_id=row.id, frozen_at=now, actor_user_id=actor_id)
    db.add(snapshot)
    db.flush()
    for team_id in teams:
        db.add(FrozenBot(snapshot_id=snapshot.id, team_id=team_id, submission_id=bots[team_id]))
    row.status = 'frozen'
    audit(db, actor_id, 'round.freeze', 'round', row.id,
          {'reason': reason, 'scheduled': scheduled, 'snapshot_id': snapshot.id, 'frozen_at': now,
           'bots': [{'team_id': t, 'submission_id': bots[t]} for t in teams]})
    db.flush()
    return snapshot


def snapshot_body(db: Session, snapshot: RoundSnapshot) -> dict[str, Any]:
    bots = db.scalars(select(FrozenBot).where(FrozenBot.snapshot_id == snapshot.id).order_by(FrozenBot.team_id))
    return {'id': s(snapshot.id), 'round_id': s(snapshot.round_id), 'frozen_at': _iso(snapshot.frozen_at),
            'bots': [{'team_id': s(b.team_id), 'submission_id': s(b.submission_id)} for b in bots]}


def _iso(value):
    from app.timeutil import iso
    return iso(value)


def run_round(db: Session, actor_id: uuid.UUID, row: Round, reason: str) -> list[Match]:
    require_enabled()
    tournament = get_tournament(db, row.tournament_id, lock=True)
    if row.status == 'draft':
        raise conflict('ROUND_NOT_FROZEN')
    if row.status != 'frozen':
        raise conflict(message='Vòng đã được chạy', round_status=row.status)
    if not _previous_finished(db, row):
        raise conflict(message='Vòng trước chưa hoàn tất', reason='previous_round_not_finished')
    snapshot = db.scalar(select(RoundSnapshot).where(RoundSnapshot.round_id == row.id))
    frozen = {b.team_id: b.submission_id for b in db.scalars(select(FrozenBot).where(FrozenBot.snapshot_id == snapshot.id))}
    created: list[Match] = []
    engine_version = tournament.engine_version
    if row.stage == 'group':
        for group in groups_of(db, tournament.id):
            members = [t for t in db.scalars(select(GroupTeam.team_id).where(GroupTeam.group_id == group.id)
                                             .order_by(GroupTeam.pot)) if t in frozen]
            for team_a, team_b in combinations(members, 2):
                match = _new_match(db, tournament, row, team_a, team_b, group_id=group.id)
                matches.create_game(db, match, 1, (team_a, frozen[team_a]), (team_b, frozen[team_b]), engine_version)
                matches.create_game(db, match, 2, (team_b, frozen[team_b]), (team_a, frozen[team_a]), engine_version)
                created.append(match)
    else:
        slots = list(db.scalars(select(BracketSlot).where(BracketSlot.tournament_id == tournament.id,
                                                          BracketSlot.round == row.stage)
                                .order_by(BracketSlot.slot_index)))
        teams = {t.id: t for t in db.scalars(select(Team).where(Team.id.in_([x.team_id for x in slots])))}
        for k in range(0, len(slots), 2):
            first, second = slots[k], slots[k + 1]
            code = f'{CODE_PREFIX[row.stage]}{k // 2 + 1}'
            match = _new_match(db, tournament, row, first.team_id, second.team_id, bracket_code=code)
            first.match_id = second.match_id = match.id
            blue, red = matches.knockout_sides(match, 1, teams)
            matches.create_game(db, match, 1, (blue, frozen[blue]), (red, frozen[red]), engine_version)
            created.append(match)
    row.status = 'running'
    if tournament.status == 'drawn':
        tournament.status = 'running'
    audit(db, actor_id, 'round.run', 'round', row.id, {'reason': reason, 'match_ids': [m.id for m in created]})
    db.flush()
    return created


def _new_match(db: Session, tournament: Tournament, row: Round, team_a: uuid.UUID, team_b: uuid.UUID,
               group_id: uuid.UUID | None = None, bracket_code: str | None = None) -> Match:
    match = Match(tournament_id=tournament.id, round_id=row.id, group_id=group_id, bracket_code=bracket_code,
                  stage=row.stage, team_a_id=team_a, team_b_id=team_b, best_of=matches.BEST_OF_BY_STAGE[row.stage],
                  status='queued')
    db.add(match)
    db.flush()
    return match


# --- cascading results ----------------------------------------------------------------------------------------

def _slot(db: Session, tournament_id: uuid.UUID, rule: str) -> BracketSlot | None:
    return db.scalar(select(BracketSlot).where(BracketSlot.tournament_id == tournament_id,
                                               BracketSlot.source_rule == rule))


def _fill_from_groups(db: Session, tournament_id: uuid.UUID, complete: bool) -> None:
    for group in groups_of(db, tournament_id):
        ranked = list(db.scalars(select(standings.Standing.team_id).where(standings.Standing.group_id == group.id)
                                 .order_by(standings.Standing.rank)))
        for position in (1, 2):
            slot = _slot(db, tournament_id, f'{group.label}{position}')
            if slot is not None:
                slot.team_id = ranked[position - 1] if complete and len(ranked) >= position else None


def _fill_from_match(db: Session, match: Match) -> None:
    if not match.bracket_code:
        return
    finished = match.status == 'finished' and match.winner_team_id is not None
    loser = None
    if finished:
        loser = match.team_b_id if match.winner_team_id == match.team_a_id else match.team_a_id
    for prefix, team in (('W', match.winner_team_id if finished else None), ('L', loser)):
        slot = _slot(db, match.tournament_id, f'{prefix}:{match.bracket_code}')
        if slot is not None:
            slot.team_id = team


def refresh_round(db: Session, row: Round) -> None:
    if row.status not in ('running', 'finished'):
        return
    statuses = list(db.scalars(select(Match.status).where(Match.round_id == row.id)))
    row.status = 'finished' if statuses and all(x == 'finished' for x in statuses) else 'running'
    tournament = db.get(Tournament, row.tournament_id)
    if row.stage in ('final', 'third_place') and tournament.status == 'running':
        final, third = stage_round(db, tournament.id, 'final'), stage_round(db, tournament.id, 'third_place')
        if final is not None and third is not None and final.status == third.status == 'finished':
            tournament.status = 'finished'
            audit(db, None, 'tournament.finished', 'tournament', tournament.id, {})


def after_match_change(db: Session, match: Match) -> None:
    """Called whenever a tournament match finishes, is reopened or overridden. Locks serialize concurrent
    callbacks so round completion, standings and bracket are computed from every committed result."""
    lock_scope(db, Tournament, match.tournament_id)
    lock_scope(db, Round, match.round_id)
    row = db.get(Round, match.round_id)
    db.refresh(row)
    if match.stage == 'group':
        lock_scope(db, Group, match.group_id)
        group = db.get(Group, match.group_id)
        standings.recompute_group(db, group)
        refresh_round(db, row)
        _fill_from_groups(db, match.tournament_id, complete=row.status == 'finished')
    else:
        _fill_from_match(db, match)
        refresh_round(db, row)
    db.flush()


def downstream_started(db: Session, match: Match) -> bool:
    tournament = db.get(Tournament, match.tournament_id)
    if tournament.status == 'finished':
        return True
    for stage in NEXT[match.stage]:
        later = stage_round(db, match.tournament_id, stage)
        if later is not None and later.status != 'draft':
            return True
    return False


def rerun_game(db: Session, actor_id: uuid.UUID, game_id: uuid.UUID, reason: str) -> tuple[Game, Game]:
    game = db.get(Game, game_id)
    if game is None:
        raise not_found('Không tìm thấy ván')
    match = matches.get_match(db, game.match_id, lock=True)
    db.refresh(game, with_for_update=True)
    if match.tournament_id is not None:
        require_enabled()
        get_tournament(db, match.tournament_id, lock=True)
        if downstream_started(db, match):
            raise conflict('DOWNSTREAM_STARTED')
    if not game.is_current:
        raise conflict(message='Chỉ chạy lại attempt hiện hành', reason='not_current')
    if game.status not in ('finished', 'infra_error'):
        raise conflict(message='Chỉ chạy lại ván đã kết thúc hoặc lỗi hạ tầng', game_status=game.status)
    if match.overridden:
        raise conflict(message='Trận đã có kết quả hành chính', reason='match_overridden')
    new = matches.new_attempt(db, match, game)
    matches.progress(db, match)
    audit(db, actor_id, 'game.rerun', 'game', game.id,
          {'reason': reason, 'match_id': match.id, 'previous_game_id': game.id, 'game_id': new.id,
           'attempt': new.attempt})
    db.flush()
    return game, new


def override_match(db: Session, actor_id: uuid.UUID, match: Match, body: dict[str, Any]) -> Match:
    if match.tournament_id is None:
        raise conflict(message='Chỉ sửa kết quả trận thuộc giải', reason='scrimmage')
    require_enabled()
    get_tournament(db, match.tournament_id, lock=True)
    if downstream_started(db, match):
        raise conflict('DOWNSTREAM_STARTED')
    if any(g.status in ('queued', 'running') for g in matches.current_games(db, match.id)):
        raise conflict(message='Trận còn ván đang chờ hoặc đang chạy', reason='games_in_progress')
    winner = uuid.UUID(body['winner_team_id']) if body['winner_team_id'] else None
    a, b = body['score_a'], body['score_b']
    if winner not in (None, match.team_a_id, match.team_b_id):
        raise invalid('winner_team_id phải là một trong hai đội', field='winner_team_id')
    consistent = ((winner == match.team_a_id and a > b) or (winner == match.team_b_id and b > a)
                  or (winner is None and a == b and match.stage == 'group'))
    if not consistent:
        raise invalid('Đội thắng và tỉ số không khớp (chỉ vòng bảng được hòa)', field='winner_team_id')
    before = {'status': match.status, 'winner_team_id': match.winner_team_id, 'score_a': match.score_a,
              'score_b': match.score_b, 'overridden': match.overridden}
    match.status, match.winner_team_id, match.score_a, match.score_b = 'finished', winner, a, b
    match.overridden, match.finished_at = True, utcnow()
    after = {'status': 'finished', 'winner_team_id': winner, 'score_a': a, 'score_b': b, 'overridden': True}
    from app.audit import jsonable
    db.add(MatchOverride(match_id=match.id, actor_user_id=actor_id, reason=body['reason'], before=jsonable(before),
                         after=jsonable(after)))
    audit(db, actor_id, 'match.override', 'match', match.id, {'reason': body['reason'], 'before': before,
                                                               'after': after})
    db.flush()
    matches.emit(db, match, 'match.finished', {'match_id': str(match.id)})
    after_match_change(db, match)
    return match


def ensure_round_status(row: Round, *allowed: str) -> None:
    if row.status not in allowed:
        raise ApiError(409, 'STATE_CONFLICT', details={'round_status': row.status})
