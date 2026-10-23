"""Smoke-build verifier using the public ottv2 engine, not devkit's stand-in."""
import asyncio
import os
import random
import time

from ottv2 import Board, GameConfig, INITIAL_FEN, run_game
from .errors import BotBuildError, InfrastructureError


class ReferenceBot:
    """Trusted in-memory random opponent using the engine's public Board API."""
    def __init__(self):
        self.started_at_ns = time.monotonic_ns()
        self.lines = []
        self.rng = random.Random(1)

    async def send_line(self, text):
        if text == "OTTV2 1":
            self.lines.append("READY SmokeOpponent")
        elif text.startswith("INIT "):
            self.side = "BLUE" if "side=BLUE" in text else "RED"
            self.lines.append("OK")
        elif text.startswith("STATE "):
            self.board = Board.from_fen(text.split()[1])
        elif text == "GO":
            self.lines.append("MOVE " + self.rng.choice(self.board.legal_moves(self.side)))

    async def read_line(self, timeout_ms):
        return self.lines.pop(0)

    async def close(self):
        pass


class EngineBuildVerifier:
    def __init__(self, sandbox=None, build_cpu=None):
        if sandbox is None:
            from .sandbox import DockerSandbox
            sandbox = DockerSandbox()
        self.sandbox = sandbox
        self.build_cpu = build_cpu or os.environ.get("RUNNER_CPUSET_BUILD", "0")

    def verify(self, image, job, timeout_seconds=150):
        if job["engine_version"] != "1.0.0":
            raise InfrastructureError("Unsupported engine version")
        config = GameConfig(engine_version="1.0.0", ruleset_id="dev-v1", map_id="standard",
                            initial_fen=INITIAL_FEN, seed=1,
                            players={"BLUE": {"team": "candidate", "submission_id": job["submission_id"]},
                                     "RED": {"team": "reference", "submission_id": "00000000-0000-4000-8000-000000000001"}})
        bot = self.sandbox.start_bot(image, self.build_cpu)
        async def smoke():
            try:
                return await asyncio.wait_for(run_game(bot, ReferenceBot(), config), timeout_seconds)
            finally:
                await bot.close()
        try:
            result = asyncio.run(smoke())
        except TimeoutError as exc:
            raise BotBuildError("Smoke game exceeded its deadline") from exc
        if result.reason in {"CRASH", "TIMEOUT", "ILLEGAL_MOVE"}:
            if result.winner == "RED":
                raise BotBuildError(f"Candidate failed smoke game: {result.reason}")
            raise InfrastructureError(f"Reference opponent failed: {result.reason}")


def make_build_verifier():
    return EngineBuildVerifier()
