import asyncio
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest

from ottv2 import Board, INITIAL_FEN
from ottv2.adapter import make_engine
from ottv2.cli import default_config
from helpers import ScriptBot

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "runner"), str(ROOT / "runner/tests"), str(ROOT / "contracts")]
import test_runtime
from ottv2_runner.engine_verifier import EngineBuildVerifier
from ottv2_runner.errors import BotBuildError
from validate import validator, replay_errors


class EngineRunnerIntegrationTests(unittest.TestCase):
    def test_real_engine_callback_and_stored_replay(self):
        class Sandbox:
            def start_bot(self, image, cpu):
                return ScriptBot(seed=int(cpu)+1)
        with tempfile.TemporaryDirectory() as tmp:
            storage = test_runtime.FakeStorage()
            runtime = test_runtime.RunnerRuntimeTests().create_runtime(
                tmp, storage=storage, engine_factory=make_engine, sandbox=Sandbox())
            callback = runtime.match(test_runtime.match_payload())
            self.assertEqual(callback["status"], "finished")
            validator("GameResultCallback").validate(callback)
            replay = json.loads(gzip.decompress(storage.objects[callback["replay_key"]][0]))
            validator("Replay").validate(replay)
            self.assertEqual(replay_errors(replay), [])
            self.assertEqual(replay["result"], callback["result"])

    def test_build_verifier_accepts_playable_bot_and_rejects_protocol_failure(self):
        for mode in (None, "startup-crash", "illegal", "timeout"):
            with self.subTest(mode=mode):
                bot = ScriptBot(mode=mode)
                class Sandbox:
                    def start_bot(self, image, cpu):
                        return bot
                verifier = EngineBuildVerifier(Sandbox())
                job = {"engine_version": "1.0.0", "submission_id": "00000001-0000-4000-8000-000000000001"}
                if mode:
                    with self.assertRaises(BotBuildError):
                        verifier.verify("test-image", job)
                else:
                    verifier.verify("test-image", job)
                self.assertTrue(bot.closed)

    def test_generated_replays_obey_schema_and_final_board(self):
        folder = ROOT / "engine/fixtures"
        for case in json.loads((folder / "manifest.json").read_text())["cases"]:
            replay = json.loads((folder / case["file"]).read_text())
            validator("Replay").validate(replay)
            self.assertEqual(replay_errors(replay), [])
            board = Board.from_fen(replay["initial_fen"])
            for move in replay["moves"]:
                board.push(move["move"], move["side"])
            self.assertEqual(board.fen(), case["expected_final_fen"])


if __name__ == "__main__":
    unittest.main()
