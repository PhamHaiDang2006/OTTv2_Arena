"""Starter-kit helpers using the engine's public board implementation."""
import random
import sys
from .board import Board, GOAL, index


def debug(text):
    for line in str(text).splitlines():
        print("# " + line, flush=True)


def choose(board, side, strategy="random", rng=None):
    moves = sorted(board.legal_moves(side))
    if not moves:
        raise ValueError("No legal moves")
    if strategy == "random":
        return (rng or random.Random(1)).choice(moves)
    goal = GOAL[side]
    def score(move):
        target = index(move[2:])
        distance = max(abs(target % 9 - goal % 9), abs(target // 9 - goal // 9))
        return target == goal, board.cells[target] is not None, -distance
    return max(moves, key=score)


def serve(select, name="PythonStarter"):
    """select(board, side, remaining_ms) -> four-character move."""
    if input() != "OTTV2 1":
        raise ValueError("Expected OTTV2 1")
    print("READY " + name, flush=True)
    line = input()
    if not line.startswith("INIT "):
        raise ValueError("Expected INIT")
    fields = dict(part.split("=", 1) for part in line.split()[1:])
    side = fields["side"]
    print("OK", flush=True)
    board, remaining = None, 0
    for raw in sys.stdin:
        line = raw.rstrip("\r\n")
        if line.startswith("STATE "):
            _, fen, turn, ply, own, opponent = line.split()
            board, remaining = Board.from_fen(fen), int(own)
            if turn != side:
                raise ValueError("Unexpected turn")
        elif line == "GO":
            if board is None:
                raise ValueError("GO before STATE")
            print("MOVE " + select(board, side, remaining), flush=True)
            board = None
        elif line.startswith("END "):
            return
        else:
            raise ValueError("Unexpected protocol command")
