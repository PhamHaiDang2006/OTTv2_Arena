"""Group standings (dev-v1 TOUR-02, contracts/rules.md).

Pair points 3/1/0. Ties on points: game_diff → games_won → head-to-head points inside the set still tied →
fewer total plies in won games → audited lot. Head-to-head is evaluated once on the tied set and not repeated
for sub-groups. The lot only happens once the group is complete; until then remaining ties are shown in seed
order (display only, not a ranking decision).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from itertools import groupby

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.audit import audit
from app.matches.service import current_games, game_winner_team
from app.models import Group, GroupTeam, Match, Standing, Team, TiebreakLot
from app.queue import add_event
from app.timeutil import utcnow
from app.tournament.draw import ALGORITHM, XorShift32, new_seed, shuffle


@dataclass
class Stats:
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    points: int = 0
    games_won: int = 0
    games_lost: int = 0
    winning_plies: int = 0

    @property
    def game_diff(self) -> int:
        return self.games_won - self.games_lost


def _pair_points(match: Match, team_id: uuid.UUID) -> int:
    if match.winner_team_id is None:
        return 1
    return 3 if match.winner_team_id == team_id else 0


def compute(db: Session, team_ids: list[uuid.UUID], finished: list[Match]) -> dict[uuid.UUID, Stats]:
    stats = {t: Stats() for t in team_ids}
    for match in finished:
        a, b = match.team_a_id, match.team_b_id
        if a not in stats or b not in stats:
            continue
        for team, own, other in ((a, match.score_a, match.score_b), (b, match.score_b, match.score_a)):
            row = stats[team]
            row.played += 1
            row.games_won += own
            row.games_lost += other
            points = _pair_points(match, team)
            row.points += points
            row.won += points == 3
            row.drawn += points == 1
            row.lost += points == 0
        if not match.overridden:
            for game in current_games(db, match.id):
                winner = game_winner_team(game)
                if winner in stats:
                    stats[winner].winning_plies += game.total_plies or 0
    return stats


def _head_to_head(block: list[uuid.UUID], finished: list[Match]) -> dict[uuid.UUID, int]:
    members = set(block)
    points = {t: 0 for t in block}
    for match in finished:
        if match.team_a_id in members and match.team_b_id in members:
            points[match.team_a_id] += _pair_points(match, match.team_a_id)
            points[match.team_b_id] += _pair_points(match, match.team_b_id)
    return points


def _lot(db: Session, group: Group, tied: list[uuid.UUID]) -> list[uuid.UUID]:
    ordered = sorted(tied, key=str)
    key = ','.join(str(t) for t in ordered)
    existing = db.scalar(select(TiebreakLot).where(TiebreakLot.group_id == group.id, TiebreakLot.team_ids_key == key))
    if existing is not None:
        return [uuid.UUID(t) for t in existing.ordered_team_ids]
    seed = new_seed()
    # Seed is audited before it is used, like the draw seed.
    audit(db, None, 'standings.tiebreak_seed', 'group', group.id, {'seed': seed, 'team_ids': ordered,
                                                                     'algorithm': ALGORITHM})
    result = shuffle(ordered, XorShift32(seed))
    db.add(TiebreakLot(group_id=group.id, team_ids_key=key, seed=seed, ordered_team_ids=[str(t) for t in result]))
    audit(db, None, 'standings.tiebreak_lot', 'group', group.id, {'seed': seed, 'order': result})
    return result


def rank(db: Session, group: Group, stats: dict[uuid.UUID, Stats], finished: list[Match], complete: bool,
         seeds: dict[uuid.UUID, int | None]) -> list[uuid.UUID]:
    primary = lambda t: (-stats[t].points, -stats[t].game_diff, -stats[t].games_won)  # noqa: E731
    order: list[uuid.UUID] = []
    for _, block_iter in groupby(sorted(stats, key=primary), key=primary):
        block = list(block_iter)
        if len(block) == 1:
            order.extend(block)
            continue
        h2h = _head_to_head(block, finished)
        secondary = lambda t: (-h2h[t], stats[t].winning_plies)  # noqa: E731, B023
        for _, sub_iter in groupby(sorted(block, key=secondary), key=secondary):
            sub = list(sub_iter)
            if len(sub) == 1:
                order.extend(sub)
            elif complete:
                order.extend(_lot(db, group, sub))
            else:
                order.extend(sorted(sub, key=lambda t: (seeds.get(t) or 10**6, str(t))))
    return order


def group_matches(db: Session, group_id: uuid.UUID) -> list[Match]:
    return list(db.scalars(select(Match).where(Match.group_id == group_id, Match.stage == 'group')))


def recompute_group(db: Session, group: Group, emit: bool = True) -> bool:
    """Rewrite standings rows for one group; returns True when every group match is finished.
    Callers hold the group row lock (after_match_change) or created the group in this transaction."""
    members = list(db.scalars(select(GroupTeam).where(GroupTeam.group_id == group.id).order_by(GroupTeam.pot)))
    team_ids = [m.team_id for m in members]
    seeds = {t.id: t.seed for t in db.scalars(select(Team).where(Team.id.in_(team_ids)))}
    matches = group_matches(db, group.id)
    finished = [m for m in matches if m.status == 'finished']
    complete = bool(matches) and len(finished) == len(matches)
    stats = compute(db, team_ids, finished)
    order = rank(db, group, stats, finished, complete, seeds)
    db.execute(delete(Standing).where(Standing.group_id == group.id))
    now = utcnow()
    for position, team_id in enumerate(order, start=1):
        row = stats[team_id]
        db.add(Standing(group_id=group.id, team_id=team_id, rank=position, played=row.played, won=row.won,
                        drawn=row.drawn, lost=row.lost, points=row.points, game_diff=row.game_diff,
                        games_won=row.games_won, winning_plies=row.winning_plies, updated_at=now))
    db.flush()
    if emit:
        add_event(db, 'standings.updated', 'public', {'tournament_id': str(group.tournament_id),
                                                      'group_id': str(group.id)})
    return complete
