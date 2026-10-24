"""Human room rules. Square delegates to engine; special maps mirror special-v1."""
from functools import lru_cache

from ottv2 import INITIAL_FEN, Board, outcome


def other(side):
    return 'RED' if side == 'BLUE' else 'BLUE'


def owner(piece):
    return 'BLUE' if piece.isupper() else 'RED'


def key(q, r):
    return f'{q},{r}'


@lru_cache
def graph(map_id):
    if map_id == 'circular':
        cells = [(q, r) for q in range(24) for r in range(4)]
        vectors = [(a, b) for a in (-1, 0, 1) for b in (-1, 0, 1) if a or b]
    else:
        cells = [(q, r) for q in range(-5, 6) for r in range(-5, 6)
                 if max(abs(q), abs(r), abs(q+r)) <= 5]
        vectors = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]
    ids = {key(q, r) for q, r in cells}
    return {key(q, r): [k for a, b in vectors
                       if (k := key((q+a) % 24 if map_id == 'circular' else q+a, r+b)) in ids]
            for q, r in cells}


def goals(map_id):
    return {'BLUE': '0,3', 'RED': '12,3'} if map_id == 'circular' else {'BLUE': '0,-5', 'RED': '0,5'}


def initial(map_id):
    if map_id == 'standard':
        return {'fen': INITIAL_FEN, 'position': {}}
    cells = [tuple(map(int, c.split(','))) for c in graph(map_id)]
    if map_id == 'circular':
        start = [(q, r) for q, r in cells if 11 <= q <= 13 and (q, r) != (12, 3)] + [(10, 3)]
    else:
        start = sorted((c for c in cells if c != (0, 5)), key=lambda c: (-c[1]-c[0]/2, c[0]))[:12]
    position = {}
    for i, (q, r) in enumerate(start):
        p = 'BPK'[i % 3]
        position[key(q, r)] = p
        position[key((q+12) % 24, r) if map_id == 'circular' else key(-q, -r)] = p.lower()
    return {'fen': None, 'position': position}


def legal(map_id, state, side):
    if map_id == 'standard':
        return [{'from': m[:2], 'to': m[2:]} for m in Board.from_fen(state['fen']).legal_moves(side)]
    pos = state['position']
    return [{'from': a, 'to': b} for a, p in pos.items() if owner(p) == side for b in graph(map_id)[a]
            if b != goals(map_id)[other(side)] and
            (b not in pos or (owner(pos[b]) != side and {'B': 'K', 'K': 'P', 'P': 'B'}[p.upper()] == pos[b].upper()))]


@lru_cache
def distances(map_id, side):
    result = {goals(map_id)[side]: 0}
    queue = list(result)
    for a in queue:
        for b in graph(map_id)[a]:
            if b not in result:
                result[b] = result[a] + 1
                queue.append(b)
    return result


def apply(map_id, state, side, move, ply):
    if move not in legal(map_id, state, side):
        raise ValueError('Nước đi không hợp lệ')
    if map_id == 'standard':
        board = Board.from_fen(state['fen']).apply(move['from']+move['to'], side)
        state['fen'] = board.fen()
        result = outcome(board, side, ply)
    else:
        pos = state['position']
        pos[move['to']] = pos.pop(move['from'])
        result = None
        if goals(map_id)[side] in pos and owner(pos[goals(map_id)[side]]) == side:
            result = side, 'GOAL'
        elif not any(owner(p) == other(side) for p in pos.values()):
            result = side, 'WIPEOUT'
        elif not legal(map_id, state, other(side)):
            result = side, 'STALEMATE'
        elif ply >= 300:
            def score(s):
                own = [(a, p) for a, p in pos.items() if owner(p) == s]
                return (min(sum(p.upper() == kind for _, p in own) for kind in 'BPK'), len(own),
                        -min([99] + [distances(map_id, s)[a] for a, _ in own]))
            result = ('BLUE' if score('BLUE') > score('RED') else 'RED'), 'MOVE_LIMIT'
    return {'winner': result[0], 'reason': result[1]} if result else None
