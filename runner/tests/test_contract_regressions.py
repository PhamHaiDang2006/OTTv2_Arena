"""Regression checks against the shared contract, without Docker services."""
import asyncio
import json
import queue
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_runtime import (
    FakeEngine, FakeStorage, build_payload, match_payload, source_zip,
)
import test_runtime
from ottv2_runner.errors import BotBuildError
from ottv2_runner.sandbox import DockerBot

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
sys.path.insert(0, str(CONTRACTS))
from validate import validator
import engine_api


class RejectVerifier:
    def verify(self, *args, **kwargs):
        raise BotBuildError("Bot never sent READY")


class StartupFailureEngine(FakeEngine):
    def __init__(self, reason):
        self.reason = reason

    async def run_game(self, blue, red, config):
        result = await super().run_game(blue, red, config)
        result.update(winner="RED", reason=self.reason)
        result["replay"]["result"].update(winner="RED", reason=self.reason)
        result["replay"]["players"]["BLUE"]["bot_name"] = ""
        validator("EngineResult").validate(result)
        return result


class ContractRegressionTests(unittest.TestCase):
    def test_failed_smoke_callback_satisfies_shared_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = source_zip()
            runtime = test_runtime.RunnerRuntimeTests().create_runtime(
                tmp, storage=FakeStorage(source), verifier=RejectVerifier(),
            )
            result = runtime.build(build_payload(source))
            self.assertEqual(result["status"], "failed")
            self.assertIsNone(result["image_tag"])
            validator("BuildResult").validate(result)

    def test_missing_ready_name_preserves_competitive_result(self):
        for reason in ("CRASH", "TIMEOUT"):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as tmp:
                runtime = test_runtime.RunnerRuntimeTests().create_runtime(
                    tmp, engine_factory=lambda: StartupFailureEngine(reason),
                )
                result = runtime.match(match_payload())
                self.assertEqual(result["status"], "finished")
                self.assertEqual(result["result"], {"winner": "RED", "reason": reason, "plies": 0})
                validator("GameResultCallback").validate(result)


class BotOutputContractTests(unittest.TestCase):
    def setUp(self):
        self.rules = json.loads((CONTRACTS / "rules/dev-v1.json").read_text())
        self.bot = DockerBot.__new__(DockerBot)
        self.bot._error = None
        self.bot._stdout_bytes = 0
        self.bot._lines = queue.Queue(maxsize=128)
        self.bot.debug = bytearray()
        self.engine_patch = patch.dict(sys.modules, {"ottv2": engine_api})
        self.engine_patch.start()
        self.addCleanup(self.engine_patch.stop)

    def test_exact_limit_including_lf_is_accepted(self):
        data = b"x" * (self.rules["max_line_bytes"] - 1)
        self.bot._drain_stdout(data + b"\n", bytearray())
        self.assertEqual(asyncio.run(self.bot.read_line(100)), data.decode())

    def test_oversized_complete_and_fragmented_lines_raise_public_error(self):
        limit = self.rules["max_line_bytes"]
        for chunks in ((b"x" * limit + b"\n",), (b"x" * (limit - 1), b"x")):
            with self.subTest(chunks=len(chunks)):
                self.bot._error = None
                pending = bytearray()
                for chunk in chunks:
                    self.bot._drain_stdout(chunk, pending)
                with self.assertRaises(engine_api.BotProtocolError):
                    asyncio.run(self.bot.read_line(100))

    def test_overflow_wakes_reader_waiting_for_newline(self):
        async def exercise():
            reader = asyncio.create_task(self.bot.read_line(1000))
            await asyncio.sleep(0.02)
            self.bot._drain_stdout(b"x" * self.rules["max_line_bytes"], bytearray())
            with self.assertRaises(engine_api.BotProtocolError):
                await asyncio.wait_for(reader, timeout=0.5)
        asyncio.run(exercise())

    def test_debug_is_truncated_but_protocol_continues(self):
        line = b"#" + b"x" * 2046 + b"\n"
        for _ in range(40):
            self.bot._drain_stdout(line, bytearray())
            asyncio.run(self.bot.read_line(100))
        self.assertEqual(len(self.bot.debug), self.rules["max_debug_bytes_per_bot"])
        self.bot._drain_stdout(b"MOVE c3d4\n", bytearray())
        self.assertEqual(asyncio.run(self.bot.read_line(100)), "MOVE c3d4")


if __name__ == "__main__":
    unittest.main()
