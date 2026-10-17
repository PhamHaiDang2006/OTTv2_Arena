"""Application-level fixed-window limits (complements Caddy, which cannot see the team)."""
from __future__ import annotations

import logging
import time

import redis

from app.errors import ApiError
from app.queue import get_redis

log = logging.getLogger('ottv2.ratelimit')


def hit(name: str, subject: str, limit: int, window_seconds: int) -> None:
    if limit <= 0:
        return
    window = int(time.time() // window_seconds)
    key = f'ottv2:rl:{name}:{subject}:{window}'
    try:
        client = get_redis()
        count = client.incr(key)
        if count == 1:
            client.expire(key, window_seconds + 1)
    except redis.RedisError as exc:
        log.warning('Rate limiter unavailable (%s); allowing request', exc)
        return
    if count > limit:
        retry = (window + 1) * window_seconds - int(time.time())
        raise ApiError(429, 'RATE_LIMITED', details={'retry_after_seconds': max(retry, 1)},
                       headers={'Retry-After': str(max(retry, 1))})
