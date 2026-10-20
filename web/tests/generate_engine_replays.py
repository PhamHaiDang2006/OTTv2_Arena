"""Cross-language acceptance fixture producer. Uses only the public engine interface.

Run from repository root with an interpreter that has `pip install -e engine`.
Output is disposable, ignored by Git, and required by the web CI cross-check.
"""
import asyncio
import json
from pathlib import Path
import random
import time

from ottv2 import Board, GameConfig, INITIAL_FEN, run_game


class RandomBot:
    def __init__(self, seed):
        self.started_at_ns = time.monotonic_ns()
        self.rng = random.Random(seed)
        self.lines = []

    async def send_line(self, line):
        if line == "OTTV2 1":
            self.lines.append("READY WebCrossCheck")
        elif line.startswith("INIT "):
            self.side = "BLUE" if "side=BLUE" in line else "RED"
            self.lines.append("OK")
        elif line.startswith("STATE "):
            self.board = Board.from_fen(line.split()[1])
        elif line == "GO":
            self.lines.append("MOVE " + self.rng.choice(sorted(self.board.legal_moves(self.side))))

    async def read_line(self, timeout_ms):
        return self.lines.pop(0)

    async def close(self):
        pass


async def main():
    cases = []
    for seed in range(100):
        config = GameConfig(
            engine_version="1.0.0", ruleset_id="dev-v1", map_id="standard",
            initial_fen=INITIAL_FEN, seed=seed,
            players={
                "BLUE": {"team": "test-blue", "submission_id": "00000001-0000-4000-8000-000000000001"},
                "RED": {"team": "test-red", "submission_id": "00000002-0000-4000-8000-000000000001"},
            },
        )
        result = await run_game(RandomBot(seed * 2), RandomBot(seed * 2 + 1), config)
        board = Board.from_fen(result.replay["initial_fen"])
        for move in result.replay["moves"]:
            board.push(move["move"], move["side"])
        cases.append({"replay": result.replay, "expected_final_fen": board.fen()})
    target = Path(__file__).parent / "generated" / "engine-replays.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(cases, separators=(",", ":")), encoding="utf-8")
    print(f"Generated {len(cases)} real engine replay cases")


if __name__ == "__main__":
    asyncio.run(main())
