"""Asynchronous referee; all process/network/storage ownership stays outside."""
import asyncio
import math
import re

from . import clock
from .api import BotProtocolError, GameConfig, GameResult, InfrastructureError
from .board import Board, other
from .rules import outcome


async def _within(awaitable, deadline):
    seconds = (deadline - clock.now_ns()) / 1_000_000_000
    # timeout_at uses asyncio's real clock; the explicit check also supports fake clocks.
    async with asyncio.timeout(max(0, seconds)):
        result = await awaitable
    if clock.now_ns() > deadline:
        raise TimeoutError
    return result


class Protocol:
    def __init__(self, bot):
        self.bot = bot
        self.name = ""
        self.debug_bytes = 0

    async def send(self, text, deadline):
        await _within(self.bot.send_line(text), deadline)

    async def read(self, deadline, debug):
        while True:
            ms = max(0, math.ceil((deadline - clock.now_ns()) / 1_000_000))
            line = await _within(self.bot.read_line(ms), deadline)
            try:
                invalid = not isinstance(line, str) or "\n" in line or "\r" in line or len(line.encode("utf-8")) + 1 > 4096
            except UnicodeError:
                invalid = True
            if invalid:
                raise BotProtocolError("Invalid protocol line")
            if line.startswith("#"):
                data = (line + "\n").encode("utf-8")
                room = 65536 - self.debug_bytes
                if room > 0:
                    fragment = data[:room].decode("utf-8", "ignore").rstrip("\n")
                    if fragment:
                        debug.append(fragment)
                    self.debug_bytes += min(room, len(data))
            elif line:
                return line
            # A fast in-memory adapter must not starve the other handshake/task.
            await asyncio.sleep(0)

    async def handshake(self, side, config):
        deadline = self.bot.started_at_ns + config.init_ms * 1_000_000
        try:
            await self.send("OTTV2 1", deadline)
            line = await self.read(deadline, [])
            if not line.startswith("READY ") or not 1 <= len(line[6:]) <= 64:
                raise BotProtocolError("Expected READY and a 1..64 character name")
            self.name = line[6:]
            await self.send(f"INIT side={side} budget_ms={config.budget_ms} init_ms={config.init_ms} max_turns={config.max_turns}", deadline)
            if await self.read(deadline, []) != "OK":
                raise BotProtocolError("Expected OK")
        except TimeoutError:
            return "TIMEOUT"
        except (EOFError, BotProtocolError):
            return "CRASH"
        return None


async def run_game(blue_io, red_io, config: GameConfig) -> GameResult:
    if not isinstance(config, GameConfig):
        raise InfrastructureError("run_game requires GameConfig")
    if (config.engine_version != "1.0.0" or config.ruleset_id != "dev-v1" or config.map_id != "standard"
            or any(type(n) is not int or n < 0 for n in (config.budget_ms, config.init_ms, config.grace_ms, config.hard_timeout_extra_ms))
            or type(config.max_turns) is not int or not 1 <= config.max_turns <= 300):
        raise InfrastructureError("Unsupported engine/profile or invalid clock configuration")
    try:
        board = Board.from_fen(config.initial_fen)
    except (ValueError, TypeError, AttributeError) as exc:
        raise InfrastructureError("Invalid initial FEN") from exc
    if set(config.players) != {"BLUE", "RED"}:
        raise InfrastructureError("Expected BLUE and RED players")
    started = clock.now_ns()
    channels = {"BLUE": Protocol(blue_io), "RED": Protocol(red_io)}
    tasks = [asyncio.create_task(channels[s].handshake(s, config)) for s in ("BLUE", "RED")]
    try:
        failures = await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    moves = []
    remaining = {"BLUE": config.budget_ms, "RED": config.budget_ms}
    decision = None
    if failures[0]:
        decision = ("RED", failures[0])
    elif failures[1]:
        decision = ("BLUE", failures[1])
    side = "BLUE"
    while decision is None:
        if not board.legal_moves(side):
            decision = (other(side), "STALEMATE")
            break
        channel, opponent = channels[side], other(side)
        debug = []
        try:
            # Writes are bounded too; thinking begins only once GO has been flushed.
            deadline = clock.now_ns() + (remaining[side] + config.hard_timeout_extra_ms) * 1_000_000
            await channel.send(f"STATE {board.fen()} {side} {len(moves)} {remaining[side]} {remaining[opponent]}", deadline)
            await channel.send("GO", deadline)
            thinking = clock.now_ns()
            deadline = thinking + (remaining[side] + config.hard_timeout_extra_ms) * 1_000_000
            line = await channel.read(deadline, debug)
            think_ms = (clock.now_ns() - thinking) // 1_000_000
            left = clock.charge(remaining[side], think_ms, config.grace_ms)
            if left < 0:
                decision = (opponent, "TIMEOUT")
                break
            match = re.fullmatch(r"MOVE ([a-i][1-9][a-i][1-9])", line)
            if match is None or not board.is_legal(match[1], side):
                decision = (opponent, "ILLEGAL_MOVE")
                break
            undo = board.push(match[1], side)
            remaining[side] = left
            moves.append({"ply": len(moves) + 1, "side": side, "move": match[1],
                          "think_ms": think_ms, "clock_ms": left, "capture": undo[3], "debug": debug})
            decision = outcome(board, side, len(moves), config.max_turns)
            side = opponent
        except TimeoutError:
            decision = (opponent, "TIMEOUT")
        except (EOFError, BotProtocolError):
            decision = (opponent, "CRASH")
    winner, reason = decision
    async def end(side):
        try:
            await channels[side].send(f"END {'WIN' if side == winner else 'LOSS'} {reason}", clock.now_ns() + 100_000_000)
        except (EOFError, TimeoutError, BotProtocolError):
            pass  # A bot that already exited cannot invalidate the result.
    await asyncio.gather(end("BLUE"), end("RED"))
    result = {"winner": winner, "reason": reason, "plies": len(moves)}
    replay = {"format": 1, "engine_version": config.engine_version, "ruleset_id": config.ruleset_id,
              "map_id": config.map_id, "initial_fen": config.initial_fen,
              "players": {s: {**config.players[s], "bot_name": channels[s].name} for s in channels},
              "moves": moves, "result": result}
    return GameResult(**result, duration_ms=(clock.now_ns() - started)//1_000_000, replay=replay)
