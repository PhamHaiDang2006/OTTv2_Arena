"""`xorshift32-fisher-yates-rejection-v1` (contracts/rules.md); vectors in contracts/fixtures/draw-cases.json."""
from __future__ import annotations

import secrets
from collections.abc import Sequence

ALGORITHM = 'xorshift32-fisher-yates-rejection-v1'
LABELS = ('A', 'B', 'C', 'D')


class XorShift32:
    def __init__(self, seed: int):
        if not 0 < seed < 2**32:
            raise ValueError('seed must be a non-zero uint32')
        self.state = seed

    def next(self) -> int:
        x = self.state
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        self.state = x
        return x

    def bounded(self, bound: int) -> int:
        limit = (2**32 // bound) * bound
        while True:
            value = self.next()
            if value < limit:
                return value % bound


def new_seed() -> int:
    return secrets.randbelow(2**32 - 1) + 1


def shuffle[T](items: Sequence[T], rng: XorShift32) -> list[T]:
    """Fisher-Yates from the last index down to 1 with bounded(i+1)."""
    result = list(items)
    for i in range(len(result) - 1, 0, -1):
        j = rng.bounded(i + 1)
        result[i], result[j] = result[j], result[i]
    return result


def draw_groups(seeds: Sequence[int], seed: int) -> dict[str, list[int]]:
    """Seeds 1..N ascending, pots of 4, one PRNG state across all pots; position 0..3 → group A..D."""
    ordered = sorted(seeds)
    if len(ordered) % 4 or ordered != list(range(1, len(ordered) + 1)):
        raise ValueError('seeds must be exactly 1..N with N a multiple of 4')
    rng = XorShift32(seed)
    groups: dict[str, list[int]] = {label: [] for label in LABELS}
    for start in range(0, len(ordered), 4):
        pot = ordered[start:start + 4]
        for i in range(3, 0, -1):
            j = rng.bounded(i + 1)
            pot[i], pot[j] = pot[j], pot[i]
        for label, team_seed in zip(LABELS, pot, strict=True):
            groups[label].append(team_seed)
    return groups
