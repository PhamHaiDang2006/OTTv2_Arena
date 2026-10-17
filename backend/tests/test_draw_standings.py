"""Draw vectors and standings tie-breaks (dev-v1 TOUR-01/TOUR-02), computed on real DB rows."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app import contract
from app.db import session_scope
from app.models import AuditLog, Game, Group, GroupTeam, Match, Standing, TiebreakLot, Tournament
from app.tournament import standings
from app.tournament.draw import XorShift32, draw_groups, shuffle
from tests.helpers import make_team


@pytest.mark.parametrize('case', contract.read_json('fixtures/draw-cases.json')['cases'],
                         ids=lambda c: f"seed{c['seed']}-n{c['team_count']}")
def test_draw_matches_shared_vectors(case):
    assert draw_groups(list(range(1, case['team_count'] + 1)), case['seed']) == case['groups']


def test_draw_rejects_bad_input():
    with pytest.raises(ValueError):
        draw_groups([1, 2, 3, 5], 42)
    with pytest.raises(ValueError):
        XorShift32(0)


def test_shuffle_is_deterministic():
    items = list(range(10))
    assert shuffle(items, XorShift32(7)) == shuffle(items, XorShift32(7))
    assert sorted(shuffle(items, XorShift32(7))) == items


class Group4:
    """A group of four teams with helpers to record finished two-game pair results."""

    def __init__(self, n: int = 4):
        self.teams = [make_team(f't{i}', seed=i) for i in range(1, n + 1)]
        with session_scope() as db:
            tournament = Tournament(name='T', engine_version='1.0.0', ruleset_id='dev-v1', status='running')
            db.add(tournament)
            db.flush()
            group = Group(tournament_id=tournament.id, label='A')
            db.add(group)
            db.flush()
            for pot, team in enumerate(self.teams):
                db.add(GroupTeam(group_id=group.id, team_id=team.id, pot=pot))
            self.tournament_id, self.group_id = tournament.id, group.id
        self.subs = {}
        from tests.helpers import make_ready_submission
        for team in self.teams:
            self.subs[team.id] = make_ready_submission(team.id, active=())
        self.matches: list[uuid.UUID] = []

    def pair(self, i: int, j: int, g1: str, g2: str, plies: tuple[int, int] = (10, 10), finished: bool = True):
        """g1/g2 = 'A' or 'B': winner team of game 1 (A blue) and game 2 (B blue)."""
        a, b = self.teams[i].id, self.teams[j].id
        with session_scope() as db:
            match = Match(tournament_id=self.tournament_id, group_id=self.group_id, stage='group', team_a_id=a,
                          team_b_id=b, best_of='two_games', status='finished' if finished else 'running')
            db.add(match)
            db.flush()
            score = {a: 0, b: 0}
            for index, (winner, ply) in enumerate(zip((g1, g2), plies, strict=True), start=1):
                blue, red = (a, b) if index == 1 else (b, a)
                side = 'BLUE' if (winner == 'A') == (blue == a) else 'RED'
                db.add(Game(match_id=match.id, game_index=index, attempt=1, is_current=True, blue_team_id=blue,
                            red_team_id=red, blue_submission_id=self.subs[blue], red_submission_id=self.subs[red],
                            map_id='standard', engine_version='1.0.0', ruleset_id='dev-v1', seed=1,
                            status='finished', winner=side, reason='GOAL', total_plies=ply))
                score[a if winner == 'A' else b] += 1
            match.score_a, match.score_b = score[a], score[b]
            match.winner_team_id = a if score[a] > score[b] else b if score[b] > score[a] else None
            self.matches.append(match.id)

    def ranking(self) -> list[int]:
        with session_scope() as db:
            group = db.get(Group, self.group_id)
            standings.recompute_group(db, group, emit=False)
            rows = list(db.scalars(select(Standing).where(Standing.group_id == group.id).order_by(Standing.rank)))
            index = {t.id: n for n, t in enumerate(self.teams)}
            return [index[r.team_id] for r in rows]

    def row(self, team_index: int) -> Standing:
        with session_scope() as db:
            return db.get(Standing, (self.group_id, self.teams[team_index].id))


def test_points_three_one_zero_and_counters():
    g = Group4(2)
    g.pair(0, 1, 'A', 'A', plies=(30, 40))
    assert g.ranking() == [0, 1]
    top, bottom = g.row(0), g.row(1)
    assert (top.points, top.won, top.games_won, top.game_diff, top.winning_plies) == (3, 1, 2, 2, 70)
    assert (bottom.points, bottom.lost, bottom.game_diff) == (0, 1, -2)


def test_draw_gives_one_point_each():
    g = Group4(2)
    g.pair(0, 1, 'A', 'B')
    g.ranking()
    assert (g.row(0).points, g.row(1).points, g.row(0).drawn) == (1, 1, 1)


def test_tiebreak_game_diff():
    g = Group4(3)
    g.pair(0, 1, 'A', 'A')  # t0 beats t1 2-0
    g.pair(1, 2, 'A', 'B')  # t1 draws t2
    g.pair(0, 2, 'B', 'B')  # t2 beats t0 2-0
    # points: t0 3, t1 1, t2 4 → t2, t0, t1
    assert g.ranking() == [2, 0, 1]


def test_tiebreak_game_diff_before_head_to_head():
    g = Group4(4)
    g.pair(0, 1, 'A', 'B')        # draw
    g.pair(0, 2, 'A', 'A')        # t0 2-0
    g.pair(1, 2, 'A', 'B')        # draw
    g.pair(1, 3, 'A', 'A')        # t1 2-0
    g.pair(0, 3, 'B', 'B')        # t3 2-0 over t0
    g.pair(2, 3, 'A', 'B')        # draw
    # t1 5 pts; t0 and t3 4 pts each, game_diff 0 and games_won 3 each; t2 2 pts.
    order = g.ranking()
    assert order[0] == 1 and order[-1] == 2
    assert set(order[1:3]) == {0, 3}
    # t0 and t3 tie on points/gd/games_won; head-to-head t3 beat t0.
    assert order[1:3] == [3, 0]


def test_tiebreak_winning_plies_after_head_to_head():
    g = Group4(2)
    g.pair(0, 1, 'A', 'B', plies=(50, 20))  # t0 wins g1 in 50, t1 wins g2 in 20 → t1 fewer plies
    assert g.ranking() == [1, 0]


def test_three_way_tie_resolved_by_head_to_head_inside_set():
    g = Group4(4)
    # Cycle among t0,t1,t2 with one 2-0 each way, everyone beats t3 2-0, and plies break the residual tie.
    g.pair(0, 1, 'A', 'A', plies=(10, 10))
    g.pair(1, 2, 'A', 'A', plies=(20, 20))
    g.pair(2, 0, 'A', 'A', plies=(30, 30))
    for i in range(3):
        g.pair(i, 3, 'A', 'A', plies=(5, 5))
    # All three: 6 pts, gd +2, games_won 4, h2h 3 each → winning plies: t0 20+10=30, t1 40+10=50, t2 60+10=70.
    assert g.ranking() == [0, 1, 2, 3]


def test_three_way_full_tie_uses_audited_lot_once():
    g = Group4(3)
    g.pair(0, 1, 'A', 'B', plies=(10, 10))
    g.pair(1, 2, 'A', 'B', plies=(10, 10))
    g.pair(0, 2, 'A', 'B', plies=(10, 10))
    first = g.ranking()
    assert sorted(first) == [0, 1, 2]
    with session_scope() as db:
        lots = list(db.scalars(select(TiebreakLot)))
        assert len(lots) == 1
        actions = [a.action for a in db.scalars(select(AuditLog).order_by(AuditLog.created_at))]
        assert actions == ['standings.tiebreak_seed', 'standings.tiebreak_lot']
        seed = lots[0].seed
        ordered = sorted([t.id for t in g.teams], key=str)
        assert [uuid.UUID(x) for x in lots[0].ordered_team_ids] == shuffle(ordered, XorShift32(seed))
    # Recomputing reuses the stored lot.
    assert g.ranking() == first
    with session_scope() as db:
        assert len(list(db.scalars(select(TiebreakLot)))) == 1


def test_incomplete_group_does_not_draw_lots():
    g = Group4(3)
    g.pair(0, 1, 'A', 'B')
    g.pair(1, 2, 'A', 'B', finished=False)
    g.ranking()
    with session_scope() as db:
        assert list(db.scalars(select(TiebreakLot))) == []


def test_unfinished_matches_are_ignored():
    g = Group4(2)
    g.pair(0, 1, 'B', 'B', finished=False)
    g.ranking()
    assert g.row(0).played == 0 and g.row(1).played == 0


def test_two_way_tie_by_points_broken_by_games_won():
    g = Group4(4)
    g.pair(0, 2, 'A', 'A')   # t0 3 pts, 2 won
    g.pair(1, 3, 'A', 'B')   # t1 1 pt
    g.pair(1, 2, 'A', 'B')   # t1 2 pts
    g.pair(0, 1, 'B', 'B')   # t1 beats t0: t1 5 pts
    g.pair(0, 3, 'A', 'B')   # t0 4 pts
    g.pair(2, 3, 'A', 'A')   # t2 4 pts
    order = g.ranking()
    assert order[0] == 1
    # t0: games 2-0, 0-2, 1-1 → gd 0, won 3 ; t2: 0-2, 1-1, 2-0 → gd 0, won 3 → head-to-head t0 beat t2.
    assert order[1:3] == [0, 2]
