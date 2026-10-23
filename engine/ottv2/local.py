"""Local process adapter for trusted development bots; this is not a sandbox."""
import asyncio
import os
from pathlib import Path
import signal
import sys
import time

from .api import BotProtocolError
from .bot import SAMPLE_BOTS

# Imports the same ottv2 package as this process, whether or not it is installed in the interpreter.
SAMPLE_BOT_SOURCE = "import sys; sys.path.insert(0, sys.argv[1]); from ottv2.bot import main; main(sys.argv[2:])"


class ProcessBot:
    @classmethod
    async def start(cls, argv):
        self = cls()
        self.started_at_ns = time.monotonic_ns()
        self.stderr = bytearray()
        self._closed = False
        self.process = await asyncio.create_subprocess_exec(
            *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, limit=4096,
            **({"start_new_session": True} if os.name != "nt" else {}),
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        return self

    async def _drain_stderr(self):
        while data := await self.process.stderr.read(8192):
            self.stderr.extend(data[:max(0, 1048576 - len(self.stderr))])

    async def send_line(self, text):
        if "\n" in text or "\r" in text:
            raise ValueError("Expected one line")
        try:
            self.process.stdin.write((text + "\n").encode())
            await self.process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise EOFError from exc

    async def read_line(self, timeout_ms):
        try:
            data = await asyncio.wait_for(self.process.stdout.readline(), timeout_ms / 1000)
        except ValueError as exc:
            raise BotProtocolError("Line exceeds 4096 bytes") from exc
        if not data:
            raise EOFError
        if len(data) > 4096 or not data.endswith(b"\n"):
            raise BotProtocolError("Oversized or unterminated line")
        try:
            return data[:-1].removesuffix(b"\r").decode("utf-8", "strict")
        except UnicodeError as exc:
            raise BotProtocolError("Invalid UTF-8") from exc

    async def close(self):
        if self._closed:
            return
        self._closed = True
        if os.name != "nt":
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif self.process.returncode is None:
            killer = await asyncio.create_subprocess_exec(
                "taskkill", "/PID", str(self.process.pid), "/T", "/F",
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                creationflags=0x08000000,
            )
            await killer.wait()
        # Resume a paused stdout transport after overflow so wait() cannot deadlock
        # on buffered data from the process we just killed.
        while await self.process.stdout.read(8192):
            pass
        await self.process.wait()
        self._stderr_task.cancel()
        await asyncio.gather(self._stderr_task, return_exceptions=True)


def bot_command(path):
    """A bot directory or entry file, or the name of a sample bot (random, greedy) when no such path exists."""
    if str(path) in SAMPLE_BOTS and not Path(path).exists():
        return [sys.executable, "-u", "-c", SAMPLE_BOT_SOURCE, str(Path(__file__).resolve().parents[1]), str(path)]
    path = Path(path).resolve()
    if path.is_dir():
        if (path / "main.py").exists():
            path /= "main.py"
        else:
            path /= "main.exe" if os.name == "nt" else "main"
    if not path.is_file():
        raise ValueError(f"Bot entrypoint not found: {path}")
    return [sys.executable, "-u", str(path)] if path.suffix == ".py" else [str(path)]
