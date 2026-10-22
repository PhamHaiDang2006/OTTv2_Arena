"""Generate fixtures from actual engine runs using deterministic in-memory BotIO."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import random
import sys
from unittest.mock import patch

from ottv2 import Board, outcome, run_game
from ottv2.board import NEIGHBORS
from ottv2.cli import default_config

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine/tests"))
from helpers import FakeClock, ScriptBot, final_fen


def main():
    folder = ROOT / "engine/fixtures"
    folder.mkdir(exist_ok=True)
    cases = [
        ("capture", "9/9/9/9/9/3k5/2B6/9/9", ["c3d4"], (), None),
        ("goal", "9/k6B1/9/9/9/9/9/9/9", ["h8i9"], (), None),
        ("crash-zero-ply", None, (), (), "startup-crash"),
        ("timeout", None, (), (), "timeout"),
        ("illegal-move", None, (), (), "illegal"),
        ("move-limit", "9/7k1/9/9/9/9/9/1B7/9", ["b2c2", "c2b2"]*75, ["h8g8", "g8h8"]*75, None),
    ]
    manifest = []
    for name, fen, blue_moves, red_moves, mode in cases:
        timer = FakeClock()
        with patch("ottv2.clock.now_ns", timer.now):
            config = default_config()
            if fen:
                config = replace(config, initial_fen=fen)
            result = asyncio.run(run_game(ScriptBot(blue_moves, mode=mode, timer=timer), ScriptBot(red_moves, timer=timer), config))
        filename = name + ".json"
        (folder / filename).write_text(json.dumps(result.replay, indent=2) + "\n")
        manifest.append({"file": filename, "expected_final_fen": final_fen(result.replay), "result": result.replay["result"]})
    (folder / "manifest.json").write_text(json.dumps({"engine_version": "1.0.0", "ruleset_id": "dev-v1", "cases": manifest}, indent=2) + "\n")
    rng = random.Random(20261016)
    positions = []
    for i in range(1000):
        cells = [rng.choice([None]*8 + list("BPKbpk")) for _ in range(81)]
        board = Board(cells)
        positions.append({"fen": board.fen(), "BLUE": sorted(board.legal_moves("BLUE")), "RED": sorted(board.legal_moves("RED"))})
    (folder / "positions.json").write_text(json.dumps({"seed": 20261016, "ruleset_id": "dev-v1", "cases": positions}, separators=(",", ":")) + "\n")
    outcomes = outcome_cases(random.Random(20261022), 600)
    (folder / "outcomes.json").write_text(json.dumps({"seed": 20261022, "ruleset_id": "dev-v1", "max_turns": 300, "cases": outcomes}, separators=(",", ":")) + "\n")
    print("Generated 6 engine replays, 1000 cross-language positions and 600 outcome cases")


def outcome_cases(rng, count):
    """One legal move on boards of varied density, then ottv2.outcome. Sparse boards reach WIPEOUT; boards with a
    lone opponent piece boxed in by its neighbours reach STALEMATE."""
    cases = []
    while len(cases) < count:
        cells = [None] * 81
        mover = rng.choice(("BLUE", "RED"))
        for square in rng.sample(range(81), rng.choice((1, 2, 3, 5, 8, 16, 30))):
            cells[square] = rng.choice("BPKbpk")
        if rng.random() < 0.3:
            lone = rng.randrange(81)
            cells = [p if p is None or p.isupper() == (mover == "BLUE") else None for p in cells]
            kind = rng.choice("BPK")
            cells[lone] = kind.lower() if mover == "BLUE" else kind
            blockers = kind + {"B": "P", "P": "K", "K": "B"}[kind]  # same kind, or the kind that beats it
            for square in NEIGHBORS[lone]:
                piece = rng.choice(blockers)
                cells[square] = piece if mover == "BLUE" else piece.lower()
        board = Board(cells)
        moves = sorted(board.legal_moves(mover))
        if not moves:
            continue
        move = rng.choice(moves)
        board.push(move, mover)
        plies = rng.choice((1, 120, 299, 300))
        result = outcome(board, mover, plies, 300)
        cases.append({"fen": board.fen(), "mover": mover, "move": move, "plies": plies,
                      "outcome": list(result) if result else None})
    reasons = {case["outcome"][1] for case in cases if case["outcome"]}
    assert reasons == {"GOAL", "WIPEOUT", "STALEMATE", "MOVE_LIMIT"}, reasons
    return cases


if __name__ == "__main__":
    main()
