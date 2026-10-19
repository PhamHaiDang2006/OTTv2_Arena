import random
from ottv2 import Board, BotProtocolError
from ottv2.board import other
from ottv2 import clock


class FakeClock:
    def __init__(self):
        self.ns = 1_000_000_000
    def now(self):
        return self.ns


class ScriptBot:
    def __init__(self, moves=(), mode=None, timer=None, delay_ms=1, seed=1):
        self.started_at_ns = clock.now_ns()
        self.lines = []
        self.moves = iter(moves)
        self.mode, self.timer, self.delay_ms = mode, timer, delay_ms
        self.rng = random.Random(seed)
        self.sent = []
        self.board = None
        self.closed = False

    async def send_line(self, text):
        self.sent.append(text)
        if text == "OTTV2 1":
            self.lines.append("READY TestBot")
        elif text.startswith("INIT "):
            self.side = "BLUE" if "side=BLUE" in text else "RED"
            self.lines.append("OK")
        elif text.startswith("STATE "):
            self.board = Board.from_fen(text.split()[1])
        elif text == "GO":
            if self.mode == "illegal":
                self.lines.append("MOVE a1a1")
            else:
                move = next(self.moves, None)
                if move is None:
                    move = self.rng.choice(sorted(self.board.legal_moves(self.side)))
                self.lines.append("MOVE " + move)

    async def read_line(self, timeout_ms):
        if self.mode == "startup-timeout":
            raise TimeoutError
        if self.mode == "startup-crash":
            raise EOFError
        if self.mode == "system":
            raise RuntimeError("host failure")
        line = self.lines.pop(0)
        if line.startswith("MOVE "):
            if self.mode == "timeout":
                raise TimeoutError
            if self.mode == "crash":
                raise BotProtocolError("invalid UTF-8")
            if self.timer:
                self.timer.ns += self.delay_ms * 1_000_000
        return line

    async def close(self):
        self.closed = True


def final_fen(replay):
    board = Board.from_fen(replay["initial_fen"])
    for move in replay["moves"]:
        board.push(move["move"], move["side"])
    return board.fen()
