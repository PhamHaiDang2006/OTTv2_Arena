"""WebSocket /ws per contracts/behavior.md.

Origin is checked at the handshake. Public channels need no auth; `team:{id}` needs an `auth` frame, accepted
during the first 10 s of the connection. Expired tokens get TOKEN_EXPIRED then close 4401 (client refreshes over
HTTP and reconnects). Frames <= 16 KiB, <= 30 messages/minute (RATE_LIMITED, close 4429), idle 60 s → 4408.
Events only carry IDs; clients refetch over HTTP.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import deque
from typing import Any

from fastapi import APIRouter, WebSocket
from starlette.concurrency import run_in_threadpool
from starlette.websockets import WebSocketDisconnect, WebSocketState

from app import contract
from app.config import get_settings
from app.db import get_sessionmaker
from app.deps import load_actor
from app.security import TokenError, decode_access_token
from app.ws.hub import hub

router = APIRouter()
MAX_FRAME_BYTES = 16 * 1024
MAX_MESSAGES_PER_MINUTE = 30
IDLE_SECONDS = 60
AUTH_WINDOW_SECONDS = 10
CLOSE_TOKEN_EXPIRED, CLOSE_IDLE, CLOSE_RATE_LIMITED, CLOSE_POLICY = 4401, 4408, 4429, 1008


class Connection:
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.opened = time.monotonic()
        self.user_id: uuid.UUID | None = None
        self.team_id: uuid.UUID | None = None
        self.is_admin = False
        self.expires_at: float | None = None  # wall-clock epoch seconds from the JWT
        self.channels: set[str] = set()
        self.received: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def send(self, message: dict[str, Any]) -> None:
        async with self._lock:
            if self.websocket.client_state == WebSocketState.CONNECTED:
                await self.websocket.send_text(json.dumps(message, ensure_ascii=False))

    async def deliver(self, event: dict[str, Any]) -> None:
        try:
            await self.send(event)
        except Exception:  # noqa: BLE001 - a dead socket is cleaned up by its receive loop
            hub.drop(self)

    async def error(self, code: str, message: str) -> None:
        await self.send({'type': 'error', 'code': code, 'message': message})


def _load(user_id: uuid.UUID):
    db = get_sessionmaker()()
    try:
        return load_actor(db, user_id)
    finally:
        db.close()


async def _handle(conn: Connection, message: dict[str, Any]) -> bool:
    """Process one valid client frame; returns False when the connection must close."""
    kind = message['type']
    if kind == 'ping':
        await conn.send({'type': 'pong'})
    elif kind == 'auth':
        if time.monotonic() - conn.opened > AUTH_WINDOW_SECONDS:
            await conn.error('UNAUTHORIZED', 'Phải gửi auth trong 10 giây đầu kết nối')
            return True
        try:
            claims = decode_access_token(message['access_token'])
        except TokenError as exc:
            if exc.expired:
                await conn.error('TOKEN_EXPIRED', 'Token đã hết hạn')
                await conn.websocket.close(code=CLOSE_TOKEN_EXPIRED)
                return False
            await conn.error('UNAUTHORIZED', 'Token không hợp lệ')
            return True
        actor = await run_in_threadpool(_load, uuid.UUID(claims['sub']))
        if actor is None:
            await conn.error('UNAUTHORIZED', 'Tài khoản không hợp lệ')
            return True
        conn.user_id, conn.team_id, conn.is_admin = actor.id, actor.team_id, actor.is_admin
        conn.expires_at = float(claims['exp'])
        await conn.send({'type': 'auth.ok'})
    elif kind == 'subscribe':
        channel = message['channel']
        if channel != 'public':
            if conn.user_id is None:
                await conn.error('UNAUTHORIZED', 'Cần xác thực trước khi đăng ký kênh đội')
                return True
            if not conn.is_admin and channel != f'team:{conn.team_id}':
                await conn.error('FORBIDDEN', 'Không có quyền với kênh này')
                return True
        if channel not in conn.channels:
            conn.channels.add(channel)
            hub.subscribe(conn, channel)
        await conn.send({'type': 'subscribed', 'channel': channel})
    elif kind == 'unsubscribe':
        channel = message['channel']
        conn.channels.discard(channel)
        hub.unsubscribe(conn, channel)
        await conn.send({'type': 'unsubscribed', 'channel': channel})
    return True


@router.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket):
    origin = (websocket.headers.get('origin') or '').rstrip('/')
    if origin not in get_settings().origins:
        await websocket.close(code=CLOSE_POLICY)  # before accept → handshake rejected (HTTP 403)
        return
    await websocket.accept()
    conn = Connection(websocket)
    try:
        while True:
            timeout = IDLE_SECONDS
            if conn.expires_at is not None:
                timeout = max(0.0, min(timeout, conn.expires_at - time.time()))
            try:
                frame = await asyncio.wait_for(websocket.receive(), timeout=timeout)
            except TimeoutError:
                if conn.expires_at is not None and time.time() >= conn.expires_at:
                    await conn.error('TOKEN_EXPIRED', 'Token đã hết hạn')
                    await websocket.close(code=CLOSE_TOKEN_EXPIRED)
                else:
                    await websocket.close(code=CLOSE_IDLE)
                return
            if frame['type'] == 'websocket.disconnect':
                return
            now = time.monotonic()
            conn.received.append(now)
            while conn.received and now - conn.received[0] > 60:
                conn.received.popleft()
            if len(conn.received) > MAX_MESSAGES_PER_MINUTE:
                await conn.error('RATE_LIMITED', 'Gửi quá nhiều tin nhắn')
                await websocket.close(code=CLOSE_RATE_LIMITED)
                return
            text = frame.get('text')
            raw = text.encode('utf-8') if text is not None else frame.get('bytes') or b''
            if len(raw) > MAX_FRAME_BYTES or text is None:
                await conn.error('INVALID_MESSAGE', 'Tin nhắn phải là JSON văn bản tối đa 16 KiB')
                continue
            try:
                message = json.loads(text)
            except ValueError:
                await conn.error('INVALID_MESSAGE', 'JSON không hợp lệ')
                continue
            if contract.errors('WsClient', message):
                await conn.error('INVALID_MESSAGE', 'Tin nhắn không đúng hợp đồng')
                continue
            if not await _handle(conn, message):
                return
    except WebSocketDisconnect:
        return
    finally:
        hub.drop(conn)
