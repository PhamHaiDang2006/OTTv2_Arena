"""Change choose_move to implement your search. Requires ottv2==1.0.0."""
import random
from ottv2.bot import choose, serve

STRATEGY = "random"  # Change to "greedy" for the greedy baseline.
rng = random.Random(1)


def choose_move(board, side, remaining_ms):
    return choose(board, side, STRATEGY, rng)


if __name__ == "__main__":
    serve(choose_move)
