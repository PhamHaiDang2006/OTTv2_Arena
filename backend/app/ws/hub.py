"""Per-process fan-out: events committed through the outbox are published on Redis and every API process
forwards them to its local WebSocket subscribers."""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any, Protocol

import redis.asyncio as aioredis

from app.config import get_settings
from app.queue import EVENTS_CHANNEL

log = logging.getLogger('ottv2.ws')


class Subscriber(Protocol):
    async def deliver(self, event: dict[str, Any]) -> None: ...


class Hub:
    def __init__(self) -> None:
        self.channels: dict[str, set[Subscriber]] = defaultdict(set)
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._listen(), name='ottv2-ws-hub')

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutting down
                pass
            self._task = None
        self.channels.clear()

    async def _listen(self) -> None:
        while True:
            client = aioredis.Redis.from_url(get_settings().redis_url)
            pubsub = client.pubsub()
            try:
                await pubsub.subscribe(EVENTS_CHANNEL)
                async for message in pubsub.listen():
                    if message.get('type') != 'message':
                        continue
                    try:
                        event = json.loads(message['data'])
                    except (TypeError, ValueError):
                        continue
                    await self.dispatch(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - reconnect to Redis
                log.warning('WebSocket hub lost Redis (%s); retrying', exc)
                await asyncio.sleep(1)
            finally:
                try:
                    await pubsub.aclose()
                    await client.aclose()
                except Exception:  # noqa: BLE001
                    pass

    async def dispatch(self, event: dict[str, Any]) -> None:
        for subscriber in list(self.channels.get(event.get('channel', ''), ())):
            await subscriber.deliver(event)

    def subscribe(self, subscriber: Subscriber, channel: str) -> None:
        self.channels[channel].add(subscriber)

    def unsubscribe(self, subscriber: Subscriber, channel: str) -> None:
        members = self.channels.get(channel)
        if members is not None:
            members.discard(subscriber)
            if not members:
                self.channels.pop(channel, None)

    def drop(self, subscriber: Subscriber) -> None:
        for channel in list(self.channels):
            self.unsubscribe(subscriber, channel)


hub = Hub()
