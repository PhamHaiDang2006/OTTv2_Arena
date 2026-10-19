import time


def now_ns():
    return time.monotonic_ns()


def charge(remaining_ms, think_ms, grace_ms=50):
    """Equality is accepted; negative remainder signals TIMEOUT."""
    return remaining_ms - max(0, think_ms - grace_ms)
