import asyncio
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from ottv2 import Board, BotProtocolError, InfrastructureError, run_game
from ottv2.board import INITIAL_FEN, index, square
from ottv2.cli import default_config
from ottv2.clock import charge
from ottv2.game import Protocol
from ottv2.rules import outcome, tiebreak
from helpers import FakeClock, ScriptBot, final_fen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "contracts"))
from validate import validator, replay_errors


class BoardTests(unittest.TestCase):
    def test_shared_fixtures_and_undo(self):
        cases = json.loads((ROOT / "contracts/fixtures/board-cases.json").read_text())["cases"]
        for case in cases:
            with self.subTest(case=case["id"]):
                board = Board.from_fen(case["initial_fen"])
                self.assertEqual(board.fen(), case["initial_fen"])
                self.assertEqual(board.is_legal(case["move"], case["side"]), case["legal"])
                if case["legal"]:
                    new = board.apply(case["move"], case["side"])
                    self.assertEqual(new.fen(), case["expected_fen"])
                    undo = board.push(case["move"], case["side"])
                    board.pop(undo)
                    self.assertEqual(board.fen(), case["initial_fen"])
                else:
                    with self.assertRaises(ValueError):
                        board.push(case["move"], case["side"])

    def test_coordinates_and_invalid_fen(self):
        for i in range(81):
            self.assertEqual(index(square(i)), i)
        for fen in ("9/9", "9/9/9/9/9/9/9/9/8", "9/9/9/9/9/9/9/9/0", "9/9/9/9/9/9/9/9/9x"):
            with self.assertRaises(ValueError):
                Board.from_fen(fen)
        for move in ("a1a1", "z1a1", "a0a1", "", "a1a9"):
            self.assertFalse(Board.from_fen(INITIAL_FEN).is_legal(move, "BLUE"))

    def test_terminal_order_and_tiebreak(self):
        cells = [None] * 81
        cells[80] = "B"
        self.assertEqual(outcome(Board(cells), "BLUE", 300), ("BLUE", "GOAL"))
        cells[80], cells[40] = None, "B"
        self.assertEqual(outcome(Board(cells), "BLUE", 300), ("BLUE", "WIPEOUT"))
        cells[0], cells[1], cells[9], cells[10] = "b", "P", "P", "P"
        self.assertEqual(outcome(Board(cells), "BLUE", 300), ("BLUE", "STALEMATE"))
        self.assertEqual(tiebreak(Board.from_fen(INITIAL_FEN)), "RED")
        # Minimum kind count outranks total material.
        cells = [None]*81
        for i,p in enumerate("BPKbbbbbb"):
            cells[20+i] = p
        self.assertEqual(tiebreak(Board(cells)), "BLUE")
        cells[21] = cells[22] = None
        self.assertEqual(tiebreak(Board(cells)), "RED")
        cells = [None]*81; cells[70] = "B"; cells[40] = "b"
        self.assertEqual(tiebreak(Board(cells)), "BLUE")


class ClockTests(unittest.TestCase):
    def test_boundaries(self):
        for remaining, elapsed, expected in ((100, 49, 100), (100, 50, 100), (100, 150, 0), (100, 151, -1), (0, 50, 0), (0, 51, -1)):
            self.assertEqual(charge(remaining, elapsed), expected)


class GameTests(unittest.TestCase):
    def game(self, blue=None, red=None, config=None):
        return asyncio.run(run_game(blue or ScriptBot(), red or ScriptBot(seed=2), config or default_config()))

    def test_protocol_failures_are_competitive_and_schema_valid(self):
        for mode, reason in (("startup-crash", "CRASH"), ("startup-timeout", "TIMEOUT"), ("crash", "CRASH"), ("timeout", "TIMEOUT"), ("illegal", "ILLEGAL_MOVE")):
            with self.subTest(mode=mode):
                result = self.game(ScriptBot(mode=mode))
                self.assertEqual((result.winner, result.reason, result.plies), ("RED", reason, 0))
                validator("EngineResult").validate(asdict(result))
                self.assertEqual(replay_errors(result.replay), [])
        result = self.game(ScriptBot(mode="startup-crash"), ScriptBot(mode="startup-timeout"))
        self.assertEqual((result.winner, result.reason), ("RED", "CRASH"))

    def test_system_failure_is_not_a_bot_loss(self):
        with self.assertRaisesRegex(RuntimeError, "host failure"):
            self.game(ScriptBot(mode="system"))

    def test_invalid_config_rejected_before_protocol(self):
        with self.assertRaises(InfrastructureError):
            self.game(config=replace(default_config(), initial_fen="invalid"))
        with self.assertRaises(InfrastructureError):
            self.game(config=replace(default_config(), ruleset_id="official"))

    def test_goal_and_capture_replay(self):
        config = replace(default_config(), initial_fen="9/k6B1/9/9/9/9/9/9/9")
        result = self.game(ScriptBot(["h8i9"]), config=config)
        self.assertEqual(result.reason, "GOAL")
        self.assertTrue(final_fen(result.replay).startswith("8B/"))
        config = replace(default_config(), initial_fen="9/9/9/9/9/3k5/2B6/9/9")
        result = self.game(ScriptBot(["c3d4"]), config=config)
        self.assertEqual(result.reason, "WIPEOUT")
        self.assertEqual(result.replay["moves"][0]["capture"], "k")

    def test_clock_equality_accepted_and_excess_rejected(self):
        for elapsed, reason, plies in ((150, "MOVE_LIMIT", 1), (151, "TIMEOUT", 0)):
            timer = FakeClock()
            with patch("ottv2.clock.now_ns", timer.now):
                config = replace(default_config(), budget_ms=100, max_turns=1)
                result = self.game(ScriptBot(timer=timer, delay_ms=elapsed), ScriptBot(timer=timer), config)
            self.assertEqual((result.reason, result.plies), (reason, plies))
            if plies:
                self.assertEqual(result.replay["moves"][0]["clock_ms"], 0)

    def test_actual_300_ply_limit_and_reproducible_replay(self):
        config = replace(default_config(), initial_fen="9/7k1/9/9/9/9/9/1B7/9")
        def play():
            timer = FakeClock()
            with patch("ottv2.clock.now_ns", timer.now):
                return self.game(ScriptBot(["b2c2", "c2b2"]*75, timer=timer),
                                 ScriptBot(["h8g8", "g8h8"]*75, timer=timer), config)
        first, second = play(), play()
        self.assertEqual(asdict(first), asdict(second))
        self.assertEqual((first.reason, first.plies), ("MOVE_LIMIT", 300))
        validator("EngineResult").validate(asdict(first))
        self.assertEqual(replay_errors(first.replay), [])

    def test_init_deadline_starts_at_process_creation(self):
        timer = FakeClock()
        with patch("ottv2.clock.now_ns", timer.now):
            blue, red = ScriptBot(), ScriptBot()
            blue.started_at_ns -= 11_000_000_000
            result = self.game(blue, red)
        self.assertEqual((result.winner, result.reason), ("RED", "TIMEOUT"))

    def test_debug_does_not_reset_read_deadline(self):
        class FloodBot:
            async def read_line(self, ms):
                timer.ns += 1_000_000
                return "# spam"
        timer = FakeClock()
        with patch("ottv2.clock.now_ns", timer.now):
            with self.assertRaises(TimeoutError):
                asyncio.run(Protocol(FloodBot()).read(timer.now() + 5_000_000, []))

    def test_malformed_handshake_and_oversized_line(self):
        class BadBot(ScriptBot):
            async def read_line(self, ms):
                return "READY " + "x" * 65
        self.assertEqual(self.game(BadBot()).reason, "CRASH")
        class LongBot(ScriptBot):
            async def read_line(self, ms):
                return "#" * 4096
        self.assertEqual(self.game(LongBot()).reason, "CRASH")


if __name__ == "__main__":
    unittest.main()
