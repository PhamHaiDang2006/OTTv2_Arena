import asyncio
import sys
import unittest
from ottv2 import BotProtocolError
from ottv2.local import ProcessBot


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


if __name__ == "__main__":
    unittest.main()
