"""Games, match jobs and match progression shared by scrimmages, tournaments, callbacks and admin actions.

Invariants (contracts/behavior.md):
- games are never updated after finished/infra_error; a retry is a new row with attempt+1 and is_current moves;
- only the backend creates attempts; automatic retry stops after attempt 4 and the match becomes `blocked`;
- match results are always recomputed from current attempts (or an administrative override).
"""
from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import contract
from app.errors import conflict, not_found
from app.models import Game, Match, Submission, Team, WorkerJob
from app.queue import add_event, add_job, team_channel
from app.timeutil import utcnow

MAX_AUTO_ATTEMPT = 4
WINS_NEEDED = {'first_to_2': 2, 'first_to_3': 3}
MAX_GAMES = {'two_games': 2, 'first_to_2': 3, 'first_to_3': 5}
BEST_OF_BY_STAGE = {'scrimmage': 'two_games', 'group': 'two_games', 'quarterfinal': 'first_to_2',
                    'semifinal': 'first_to_2', 'third_place': 'first_to_3', 'final': 'first_to_3'}


def queue_for(match: Match) -> str:
    return 'match:scrimmage' if match.stage == 'scrimmage' else 'match:tournament'


def game_config(engine_version: str, players: dict, seed: int) -> dict:
    return {'engine_version': engine_version, 'ruleset_id': 'dev-v1', 'map_id': contract.MAP_ID,
            'initial_fen': contract.INITIAL_FEN, 'players': players, **contract.GAME_LIMITS, 'seed': seed}


def _enqueue_game(db: Session, match: Match, game: Game, teams: dict[uuid.UUID, Team],
                  submissions: dict[uuid.UUID, Submission]) -> None:
    blue, red = submissions[game.blue_submission_id], submissions[game.red_submission_id]
    for submission in (blue, red):
        if submission.engine_version != game.engine_version:
            raise conflict('SUBMISSION_NOT_READY', 'Bot cần được build bằng phiên bản engine của ván',
                           reason='engine_version_mismatch', submission_id=str(submission.id),
                           expected=game.engine_version, actual=submission.engine_version)
    players = {'BLUE': {'team': teams[game.blue_team_id].slug, 'submission_id': str(blue.id)},
               'RED': {'team': teams[game.red_team_id].slug, 'submission_id': str(red.id)}}
    job_id = uuid.uuid4()
    payload = {'schema_version': contract.SCHEMA_VERSION, 'job_id': str(job_id), 'game_id': str(game.id),
               'attempt': game.attempt, 'blue_image': blue.image_tag, 'red_image': red.image_tag,
               'map_id': game.map_id, 'engine_version': game.engine_version, 'players': players,
               'config': game_config(game.engine_version, players, game.seed)}
    problems = contract.errors('MatchJob', payload)
    if problems:
        raise RuntimeError(f'MatchJob violates contract: {problems}')
    add_job(db, WorkerJob(id=job_id, kind='match', queue=queue_for(match), game_id=game.id, attempt=game.attempt,
                          payload=payload))


def _load(db: Session, team_ids: set[uuid.UUID], submission_ids: set[uuid.UUID]):
    teams = {t.id: t for t in db.scalars(select(Team).where(Team.id.in_(team_ids)))}
    subs = {x.id: x for x in db.scalars(select(Submission).where(Submission.id.in_(submission_ids)))}
    return teams, subs


def create_game(db: Session, match: Match, game_index: int, blue: tuple[uuid.UUID, uuid.UUID],
                red: tuple[uuid.UUID, uuid.UUID], engine_version: str, seed: int | None = None,
                attempt: int = 1) -> Game:
    """blue/red are (team_id, submission_id); submissions must be ready (image_tag set)."""
    game = Game(id=uuid.uuid4(), match_id=match.id, game_index=game_index, attempt=attempt, is_current=True,
                blue_team_id=blue[0], blue_submission_id=blue[1], red_team_id=red[0], red_submission_id=red[1],
                map_id=contract.MAP_ID, engine_version=engine_version, ruleset_id='dev-v1',
                seed=secrets.randbits(32) if seed is None else seed, status='queued')
    db.add(game)
    db.flush()
    teams, subs = _load(db, {blue[0], red[0]}, {blue[1], red[1]})
    _enqueue_game(db, match, game, teams, subs)
    return game


def new_attempt(db: Session, match: Match, previous: Game) -> Game:
    """Same pairing, sides, submissions and seed; fresh game_id and job_id."""
    previous.is_current = False
    db.flush()
    return create_game(db, match, previous.game_index, (previous.blue_team_id, previous.blue_submission_id),
                       (previous.red_team_id, previous.red_submission_id), previous.engine_version,
                       seed=previous.seed, attempt=previous.attempt + 1)


def current_games(db: Session, match_id: uuid.UUID) -> list[Game]:
    return list(db.scalars(select(Game).where(Game.match_id == match_id, Game.is_current).order_by(Game.game_index)))


def game_winner_team(game: Game) -> uuid.UUID | None:
    if game.status != 'finished':
        return None
    return game.blue_team_id if game.winner == 'BLUE' else game.red_team_id


@dataclass
class Evaluation:
    status: str
    score_a: int
    score_b: int
    winner_team_id: uuid.UUID | None
    next_game_index: int | None = None
    counted_games: tuple[uuid.UUID, ...] = ()


def evaluate(match: Match, games: list[Game]) -> Evaluation:
    """Result of a match from its current games, in game order."""
    by_index = {g.game_index: g for g in games}
    score = {match.team_a_id: 0, match.team_b_id: 0}
    counted: list[uuid.UUID] = []
    blocked = any(g.status == 'infra_error' and g.attempt >= MAX_AUTO_ATTEMPT for g in games)
    started = any(g.status in ('running', 'finished', 'infra_error') for g in games)
    if match.best_of == 'two_games':
        complete = True
        for index in (1, 2):
            game = by_index.get(index)
            if game is None or game.status != 'finished':
                complete = False
                continue
            score[game_winner_team(game)] += 1
            counted.append(game.id)
        a, b = score[match.team_a_id], score[match.team_b_id]
        if complete:
            winner = match.team_a_id if a > b else match.team_b_id if b > a else None
            return Evaluation('finished', a, b, winner, counted_games=tuple(counted))
        return Evaluation('blocked' if blocked else 'running' if started else 'queued', a, b, None,
                          counted_games=tuple(counted))
    needed = WINS_NEEDED[match.best_of]
    for index in range(1, MAX_GAMES[match.best_of] + 1):
        game = by_index.get(index)
        if game is None:
            a, b = score[match.team_a_id], score[match.team_b_id]
            return Evaluation('blocked' if blocked else 'running', a, b, None, next_game_index=index,
                              counted_games=tuple(counted))
        if game.status != 'finished':
            break
        score[game_winner_team(game)] += 1
        counted.append(game.id)
        if max(score.values()) >= needed:
            a, b = score[match.team_a_id], score[match.team_b_id]
            return Evaluation('finished', a, b, match.team_a_id if a > b else match.team_b_id,
                              counted_games=tuple(counted))
    a, b = score[match.team_a_id], score[match.team_b_id]
    return Evaluation('blocked' if blocked else 'running' if started else 'queued', a, b, None,
                      counted_games=tuple(counted))


def knockout_sides(match: Match, game_index: int, teams: dict[uuid.UUID, Team]) -> tuple[uuid.UUID, uuid.UUID]:
    """dev-v1 TOUR-02: odd games A is BLUE, even games B is BLUE; the last possible game goes BLUE to the
    stronger seed (smaller seed number). Returns (blue_team_id, red_team_id)."""
    a, b = match.team_a_id, match.team_b_id
    if game_index == MAX_GAMES[match.best_of]:
        seed_a, seed_b = teams[a].seed, teams[b].seed
        if seed_a is not None and seed_b is not None and seed_b < seed_a:
            return b, a
        return a, b
    return (a, b) if game_index % 2 == 1 else (b, a)


def match_channels(match: Match) -> list[str]:
    if match.stage == 'scrimmage':
        return [team_channel(match.team_a_id), team_channel(match.team_b_id)]
    return ['public']


def emit(db: Session, match: Match, event_type: str, data: dict) -> None:
    for channel in match_channels(match):
        add_event(db, event_type, channel, data)


def get_match(db: Session, match_id: uuid.UUID, lock: bool = False) -> Match:
    match = db.get(Match, match_id, with_for_update=lock)
    if match is None:
        raise not_found('Không tìm thấy trận')
    return match


def can_view(match: Match, team_id: uuid.UUID | None, is_admin: bool) -> bool:
    """Tournament matches: any signed-in user. Scrimmages: the two teams and admins."""
    if match.stage != 'scrimmage' or is_admin:
        return True
    return team_id is not None and team_id in (match.team_a_id, match.team_b_id)


def frozen_submission(db: Session, round_id: uuid.UUID, team_id: uuid.UUID) -> uuid.UUID:
    from app.models import FrozenBot, RoundSnapshot
    sub = db.scalar(select(FrozenBot.submission_id).join(RoundSnapshot, RoundSnapshot.id == FrozenBot.snapshot_id)
                    .where(RoundSnapshot.round_id == round_id, FrozenBot.team_id == team_id))
    if sub is None:
        raise RuntimeError(f'No frozen bot for team {team_id} in round {round_id}')
    return sub


def progress(db: Session, match: Match) -> None:
    """Recompute match state from current games; create the next knockout game; cascade to tournament logic."""
    if match.overridden:
        return
    games = current_games(db, match.id)
    evaluation = evaluate(match, games)
    was_finished = match.status == 'finished'
    match.score_a, match.score_b = evaluation.score_a, evaluation.score_b
    if evaluation.status == 'finished':
        changed = not was_finished or match.winner_team_id != evaluation.winner_team_id
        match.status, match.winner_team_id = 'finished', evaluation.winner_team_id
        match.finished_at = match.finished_at if was_finished and not changed else utcnow()
        db.flush()
        if changed:
            emit(db, match, 'match.finished', {'match_id': str(match.id)})
        if match.tournament_id is not None:
            from app.tournament import service as tournament
            tournament.after_match_change(db, match)
        return
    match.winner_team_id, match.finished_at = None, None
    if evaluation.next_game_index is not None and evaluation.status != 'blocked':
        teams = {t.id: t for t in db.scalars(select(Team).where(Team.id.in_([match.team_a_id, match.team_b_id])))}
        blue_team, red_team = knockout_sides(match, evaluation.next_game_index, teams)
        engine_version = games[0].engine_version
        create_game(db, match, evaluation.next_game_index,
                    (blue_team, frozen_submission(db, match.round_id, blue_team)),
                    (red_team, frozen_submission(db, match.round_id, red_team)), engine_version)
        evaluation.status = 'running'
    match.status = evaluation.status
    db.flush()
    if was_finished and match.tournament_id is not None:
        from app.tournament import service as tournament
        tournament.after_match_change(db, match)
