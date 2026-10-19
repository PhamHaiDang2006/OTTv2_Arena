"""Generate fixtures from actual engine runs using deterministic in-memory BotIO."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import random
import sys
from unittest.mock import patch

from ottv2 import Board, run_game
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
    print("Generated 6 engine replays and 1000 cross-language positions")


if __name__ == "__main__":
    main()
