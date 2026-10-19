"""Public types implementing contracts/engine_api.py, contract v1.0.0."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict

Side = Literal['BLUE', 'RED']
Reason = Literal['GOAL', 'WIPEOUT', 'STALEMATE', 'TIMEOUT', 'ILLEGAL_MOVE', 'CRASH', 'MOVE_LIMIT']


class Player(TypedDict):
    team: str
    submission_id: str


class Players(TypedDict):
    BLUE: Player
    RED: Player


class ReplayPlayer(Player):
    bot_name: str


class ReplayPlayers(TypedDict):
    BLUE: ReplayPlayer
    RED: ReplayPlayer


class MoveRecord(TypedDict):
    ply: int
    side: Side
    move: str
    think_ms: int
    clock_ms: int
    capture: str | None
    debug: list[str]


class Result(TypedDict):
    winner: Side
    reason: Reason
    plies: int


class Replay(TypedDict):
    format: Literal[1]
    engine_version: str
    ruleset_id: Literal['dev-v1']
    map_id: Literal['standard']
    initial_fen: str
    players: ReplayPlayers
    moves: list[MoveRecord]
    result: Result


@dataclass(frozen=True)
class GameConfig:
    engine_version: str
    ruleset_id: Literal['dev-v1']
    map_id: Literal['standard']
    initial_fen: str
    players: Players
    seed: int
    budget_ms: int = 60000
    init_ms: int = 10000
    grace_ms: int = 50
    hard_timeout_extra_ms: int = 1000
    max_turns: int = 300


@dataclass(frozen=True)
class GameResult:
    winner: Side
    reason: Reason
    plies: int
    duration_ms: int
    replay: Replay


class BotProtocolError(Exception):
    """Adapter detected invalid UTF-8/oversized bot line; classify as bot CRASH."""


class InfrastructureError(Exception):
    """Engine/adapter failure not attributable to bot; no competitive result."""


class BotIO(Protocol):
    started_at_ns: int  # same host monotonic clock as engine

    async def send_line(self, text: str) -> None:
        """Append LF, flush; caller enforces write deadline too."""
        ...

    async def read_line(self, timeout_ms: int) -> str:
        """Return UTF-8 without LF; EOFError, TimeoutError or BotProtocolError."""
        ...

    async def close(self) -> None:
        """Idempotent pipe close; runner still owns process/container cleanup."""
        ...


class RunGame(Protocol):
    async def __call__(self, blue_io: BotIO, red_io: BotIO, config: GameConfig) -> GameResult: ...
