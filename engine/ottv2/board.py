"""dev-v1 board. a1=0, i9=80. apply is immutable; push/pop support search."""
import re

INITIAL_FEN = "9/pbkpbkpbk/kpbkpbkpb/9/9/9/BPKBPKBPK/KBPKBPKBP/9"
CAPTURE = {"B": "K", "K": "P", "P": "B"}
GOAL = {"BLUE": 80, "RED": 0}
SQUARES = tuple(chr(97 + i % 9) + str(i // 9 + 1) for i in range(81))
NEIGHBORS = tuple(tuple(y * 9 + x for y in range(max(0, i//9-1), min(9, i//9+2))
                        for x in range(max(0, i%9-1), min(9, i%9+2)) if y*9+x != i)
                  for i in range(81))


def other(side):
    if side not in GOAL:
        raise ValueError("Side must be BLUE or RED")
    return "RED" if side == "BLUE" else "BLUE"


def square(index):
    if not 0 <= index < 81:
        raise ValueError("Square index out of range")
    return chr(97 + index % 9) + str(index // 9 + 1)


def index(square_name):
    if not re.fullmatch(r"[a-i][1-9]", square_name):
        raise ValueError("Invalid square")
    return (int(square_name[1]) - 1) * 9 + ord(square_name[0]) - 97


class Board:
    def __init__(self, cells):
        self.cells = list(cells)
        if len(self.cells) != 81 or any(p not in (None, "B", "P", "K", "b", "p", "k") for p in self.cells):
            raise ValueError("Expected 81 valid cells")

    @classmethod
    def from_fen(cls, fen):
        ranks = fen.split("/")
        if len(ranks) != 9:
            raise ValueError("Expected nine ranks")
        cells = []
        for rank in reversed(ranks):
            row = []
            for token in rank:
                if token in "123456789":
                    row.extend([None] * int(token))
                elif token in "BPKbpk":
                    row.append(token)
                else:
                    raise ValueError("Invalid FEN token")
            if len(row) != 9:
                raise ValueError("Each rank must contain nine cells")
            cells.extend(row)
        return cls(cells)

    def fen(self):
        ranks = []
        for y in reversed(range(9)):
            text, empty = "", 0
            for p in self.cells[y*9:y*9+9]:
                if p is None:
                    empty += 1
                else:
                    text += (str(empty) if empty else "") + p
                    empty = 0
            ranks.append(text + (str(empty) if empty else ""))
        return "/".join(ranks)

    def pieces(self, side, kind=None):
        other(side)
        return [i for i, p in enumerate(self.cells)
                if p and p.isupper() == (side == "BLUE") and (kind is None or p.upper() == kind)]

    def legal_moves(self, side):
        forbidden = GOAL[other(side)]
        result = []
        for a in self.pieces(side):
            p = self.cells[a]
            for b in NEIGHBORS[a]:
                q = self.cells[b]
                if b == forbidden:
                    continue
                if q is None or (q.isupper() != p.isupper() and CAPTURE[p.upper()] == q.upper()):
                    result.append(SQUARES[a] + SQUARES[b])
        return result

    def is_legal(self, move, side):
        if not isinstance(move, str) or not re.fullmatch(r"[a-i][1-9]{1}[a-i][1-9]", move):
            return False
        a, b = index(move[:2]), index(move[2:])
        p, q = self.cells[a], self.cells[b]
        return bool(p and p.isupper() == (side == "BLUE") and b in NEIGHBORS[a]
                    and b != GOAL[other(side)] and
                    (q is None or (q.isupper() != p.isupper() and CAPTURE[p.upper()] == q.upper())))

    def push(self, move, side):
        if not self.is_legal(move, side):
            raise ValueError("Illegal move")
        a, b = index(move[:2]), index(move[2:])
        undo = (a, b, self.cells[a], self.cells[b])
        self.cells[b], self.cells[a] = self.cells[a], None
        return undo

    def pop(self, undo):
        a, b, p, captured = undo
        self.cells[a], self.cells[b] = p, captured

    def apply(self, move, side):
        board = Board(self.cells)
        board.push(move, side)
        return board
