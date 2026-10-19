from .board import GOAL, other


def tiebreak(board):
    def score(side):
        pieces = board.pieces(side)
        counts = [len(board.pieces(side, p)) for p in "BPK"]
        goal = GOAL[side]
        distance = min((max(abs(i % 9 - goal % 9), abs(i // 9 - goal // 9)) for i in pieces), default=9)
        return min(counts), len(pieces), -distance
    return "BLUE" if score("BLUE") > score("RED") else "RED"


def outcome(board, mover, plies, max_turns=300):
    opponent = other(mover)
    goal_piece = board.cells[GOAL[mover]]
    if goal_piece and goal_piece.isupper() == (mover == "BLUE"):
        return mover, "GOAL"
    if not board.pieces(opponent):
        return mover, "WIPEOUT"
    if not board.legal_moves(opponent):
        return mover, "STALEMATE"
    if plies >= max_turns:
        return tiebreak(board), "MOVE_LIMIT"
    return None
