import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from ottv2 import BotProtocolError
from ottv2.local import ProcessBot, bot_command

ENGINE = Path(__file__).resolve().parents[1]


class LocalPipeTests(unittest.TestCase):
    def test_bad_output_and_cleanup(self):
        async def check(source, error):
            bot = await ProcessBot.start([sys.executable, "-u", "-c", source])
            try:
                with self.assertRaises(error):
                    await bot.read_line(2000)
            finally:
                await asyncio.wait_for(bot.close(), 5)
                await bot.close()
            self.assertIsNotNone(bot.process.returncode)
        for source, error in (
            ("import sys; sys.stdout.buffer.write(b'\\xff\\n'); sys.stdout.flush()", BotProtocolError),
            ("print('x'*100000, flush=True)", BotProtocolError),
            ("import sys; sys.stdout.write('unterminated'); sys.stdout.flush()", BotProtocolError),
            ("pass", EOFError),
            ("import time; time.sleep(30)", TimeoutError),
        ):
            with self.subTest(source=source):
                asyncio.run(check(source, error))

    def test_stderr_is_drained_and_bounded(self):
        async def check():
            source = "import sys; sys.stderr.write('x'*2000000); sys.stderr.flush(); print('READY test', flush=True)"
            bot = await ProcessBot.start([sys.executable, "-u", "-c", source])
            try:
                self.assertEqual(await bot.read_line(5000), "READY test")
                self.assertEqual(len(bot.stderr), 1048576)
            finally:
                await bot.close()
        asyncio.run(check())


class PracticeTests(unittest.TestCase):
    def test_sample_bot_names_start_protocol_bots(self):
        async def check(name):
            bot = await ProcessBot.start(bot_command(name))
            try:
                await bot.send_line("OTTV2 1")
                self.assertEqual(await bot.read_line(5000), "READY Sample-" + name)
            finally:
                await bot.close()
        for name in ("random", "greedy"):
            with self.subTest(name=name):
                asyncio.run(check(name))

    def test_existing_path_wins_over_sample_name(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "greedy").mkdir()
            (Path(folder) / "greedy" / "main.py").write_text("")
            cwd = os.getcwd()
            os.chdir(folder)
            try:
                self.assertEqual(bot_command("greedy")[-1], str(Path(folder, "greedy", "main.py").resolve()))
            finally:
                os.chdir(cwd)

    def test_practice_alternates_colours_and_reports_total(self):
        with tempfile.TemporaryDirectory() as folder:
            replay = Path(folder) / "practice" / "replay.json"
            env = {**os.environ, "PYTHONPATH": str(ENGINE)}
            done = subprocess.run([sys.executable, "-m", "ottv2", "practice", "random", "--vs", "greedy", "--games", "2",
                                   "--replay", str(replay)], capture_output=True, text=True, env=env, timeout=120)
            self.assertEqual(done.returncode, 0, done.stderr)
            lines = done.stdout.splitlines()
            self.assertEqual(len(lines), 3)
            self.assertRegex(lines[-1], r"^Total: random \d - \d greedy$")
            wins = [int(x) for x in lines[-1].split() if x.isdigit()]
            self.assertEqual(sum(wins), 2)
            names = []
            for game in (1, 2):
                data = json.loads((replay.parent / f"replay-{game}.json").read_text(encoding="utf-8"))
                self.assertEqual(data["result"]["plies"], len(data["moves"]))
                names.append((data["players"]["BLUE"]["bot_name"], data["players"]["RED"]["bot_name"]))
            self.assertEqual(names, [("Sample-random", "Sample-greedy"), ("Sample-greedy", "Sample-random")])


if __name__ == "__main__":
    unittest.main()
