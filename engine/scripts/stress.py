"""Seeded rule-level self-play and replay validation; not a timing benchmark."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import random
import time

from ottv2 import Board, INITIAL_FEN
from ottv2.board import other
from ottv2.rules import outcome


def play(seed):
    rng = random.Random(seed)
    board = Board.from_fen(INITIAL_FEN)
    side, moves = "BLUE", []
    for ply in range(1, 301):
        legal = board.legal_moves(side)
        if not legal:
            return moves, (other(side), "STALEMATE"), board.fen()
        move = rng.choice(legal)
        undo = board.push(move, side)
        moved = board.cells.copy()
        board.pop(undo)
        # Undo and replay must recover exactly the same position.
        board.push(move, side)
        assert board.cells == moved
        moves.append(move)
        result = outcome(board, side, ply)
        if result:
            return moves, result, board.fen()
        side = other(side)
    raise AssertionError("No result at ply 300")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=10000)
    parser.add_argument("--output", default="engine/fixtures/stress-report.json")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    started = time.monotonic()
    counts, digest = Counter(), hashlib.sha256()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for seed, first in enumerate(pool.map(check_seed, range(args.games), chunksize=25)):
            counts[first[1][0]] += 1
            counts[first[1][1]] += 1
            digest.update(json.dumps(first, separators=(",", ":")).encode())
            if (seed + 1) % 1000 == 0:
                print(f"{seed + 1}/{args.games} games checked", flush=True)
    report = {"engine_version": "1.0.0", "ruleset_id": "dev-v1", "games": args.games,
              "seeds": [0, args.games - 1], "deterministic": True, "counts": dict(counts),
              "blue_win_percent": round(100 * counts["BLUE"] / args.games, 2),
              "result_sha256": digest.hexdigest(), "elapsed_seconds": round(time.monotonic() - started, 2)}
    path = Path(args.output); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


def check_seed(seed):
    result = play(seed)
    assert result == play(seed), f"Non-deterministic seed {seed}"
    return result


if __name__ == "__main__":
    main()
