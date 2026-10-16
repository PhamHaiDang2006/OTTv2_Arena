from __future__ import annotations

import threading
import uuid
from typing import Any, Callable

from .errors import LeaseLost

LEASE_TTL_MS = 90_000
RENEW_EVERY_SECONDS = 15
_RENEW_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('PEXPIRE', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


class RedisLease:
    def __init__(self, client: Any, job_id: str, token: str | None = None, ttl_ms: int = LEASE_TTL_MS):
        self.client = client
        self.job_id = job_id
        self.token = token or str(uuid.uuid4())
        self.ttl_ms = ttl_ms
        self.key = f"ottv2:lease:{job_id}"

    def claim(self) -> bool:
        return bool(self.client.set(self.key, self.token, nx=True, px=self.ttl_ms))

    def renew(self) -> bool:
        return bool(self.client.eval(_RENEW_LUA, 1, self.key, self.token, self.ttl_ms))

    def release(self) -> bool:
        return bool(self.client.eval(_RELEASE_LUA, 1, self.key, self.token))

    def is_owner(self) -> bool:
        value = self.client.get(self.key)
        if isinstance(value, bytes):
            value = value.decode("ascii", "strict")
        return value == self.token


class LeaseHeartbeat:
    def __init__(
        self,
        lease: RedisLease,
        interval: float = RENEW_EVERY_SECONDS,
        on_lost: Callable[[], None] | None = None,
    ):
        self.lease = lease
        self.interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="runner-lease-renew", daemon=True)
        self._lost = False
        self._lost_lock = threading.Lock()
        self._on_lost = on_lost

    def _mark_lost(self) -> None:
        with self._lost_lock:
            if self._lost:
                return
            self._lost = True
        if self._on_lost:
            try:
                self._on_lost()
            except Exception:
                pass

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                if not self.lease.renew():
                    self._mark_lost()
                    return
            except Exception:
                self._mark_lost()
                return

    def check(self) -> None:
        if self._lost:
            raise LeaseLost("Worker lease was lost")
        try:
            owner = self.lease.is_owner()
        except Exception as exc:
            self._mark_lost()
            raise LeaseLost("Could not confirm worker lease ownership") from exc
        if not owner:
            self._mark_lost()
            raise LeaseLost("Worker lease is no longer owned by this worker")

    def close(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=min(2.0, self.interval + 0.1))
