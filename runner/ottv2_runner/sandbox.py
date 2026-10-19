from __future__ import annotations

import asyncio
import importlib
import io
import os
import queue
import re
import socket
import struct
import tarfile
import threading
import time
import tempfile
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .errors import BotBuildError, InfrastructureError, UnsupportedLanguage

MAX_BUILD_LOG_BYTES = 1024 * 1024
MAX_BOT_STDERR_BYTES = 1024 * 1024
MAX_BOT_DEBUG_BYTES = 64 * 1024
MAX_BOT_STDOUT_BYTES = 1024 * 1024
MAX_BOT_LINE_BYTES = 4096  # Includes the terminating LF (dev-v1).


@dataclass(frozen=True)
class BuildSpec:
    language: str
    runtime_image: str
    builder_image: str
    entrypoint: tuple[str, ...]
    enabled: bool


class BotIO(Protocol):
    started_at_ns: int

    async def send_line(self, text: str) -> None: ...
    async def read_line(self, timeout_ms: int) -> str: ...
    async def close(self) -> None: ...


class BotProtocolError(Exception):
    """Bot emitted invalid UTF-8, an oversized line, or exceeded output bounds."""


def _protocol_error(message: str) -> Exception:
    try:
        engine_module = importlib.import_module("ottv2")
        error_type = getattr(engine_module, "BotProtocolError")
    except (ImportError, AttributeError):
        error_type = BotProtocolError
    return error_type(message)


def _infrastructure_error(message: str) -> Exception:
    try:
        engine_module = importlib.import_module("ottv2")
        error_type = getattr(engine_module, "InfrastructureError")
    except (ImportError, AttributeError):
        error_type = InfrastructureError
    return error_type(message)


class Sandbox(Protocol):
    def build(self, language: str, source_dir: Path, submission_id: str) -> str: ...
    def start_bot(self, image: str, cpu: str) -> BotIO: ...


def build_specs() -> dict[str, BuildSpec]:
    specs: dict[str, BuildSpec] = {}
    for language, entrypoint in {
        "python": ("python", "-u", "/bot/main.py"),
        "cpp": ("/bot/main",),
        "java": ("java", "-cp", "/bot", "Main"),
        "node": ("node", "/bot/main.js"),
    }.items():
        value = os.environ.get(f"RUNNER_IMAGE_{language.upper()}", "")
        builder = os.environ.get(f"RUNNER_BUILD_IMAGE_{language.upper()}", value)
        enabled = language in {"python", "cpp"} or (
            language == "java" and os.environ.get("RUNNER_ENABLE_JAVA", "false").lower() == "true"
        ) or (
            language == "node" and os.environ.get("RUNNER_ENABLE_NODE", "false").lower() == "true"
        )
        specs[language] = BuildSpec(language, value, builder, entrypoint, enabled)
    return specs


class DockerSandbox:
    """Docker SDK adapter. All commands and Dockerfiles are runner-owned constants."""

    def __init__(self, docker_client: Any | None = None, specs: dict[str, BuildSpec] | None = None):
        if docker_client is None:
            try:
                import docker
                docker_client = docker.from_env()
            except Exception as exc:
                raise InfrastructureError("Docker SDK/daemon is unavailable") from exc
        self.client = docker_client
        self.specs = specs or build_specs()
        self.last_build_log = b""
        self._active_build_container: Any | None = None
        self._active_build_lock = threading.Lock()

    def abort_current_build(self) -> None:
        with self._active_build_lock:
            container = self._active_build_container
        if container is not None:
            try:
                container.kill()
            except Exception:
                pass

    @staticmethod
    def _validate_image(image: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[a-f0-9]{64}", image):
            raise InfrastructureError("Configured runner image must be pinned by SHA-256 digest")

    def build(self, language: str, source_dir: Path, submission_id: str) -> str:
        spec = self.specs[language]
        if not spec.enabled:
            raise UnsupportedLanguage(f"{language} support is disabled pending sandbox certification")
        self._validate_image(spec.runtime_image)
        self._ensure_image(spec.runtime_image)
        if language in {"cpp", "java"}:
            self._validate_image(spec.builder_image)
            self._ensure_image(spec.builder_image)
        compiled: Path | None = None
        if language in {"cpp", "java"}:
            compiled = self._compile(spec, source_dir)
        context = io.BytesIO()
        with tarfile.open(fileobj=context, mode="w") as tar:
            for path in sorted(source_dir.rglob("*")):
                if path.is_file():
                    tar.add(path, arcname=path.relative_to(source_dir).as_posix(), recursive=False)
            if compiled is not None:
                for path in sorted(compiled.rglob("*")):
                    if path.is_file():
                        member = tar.gettarinfo(path, arcname=f"compiled/{path.relative_to(compiled).as_posix()}")
                        member.mode = 0o755
                        member.uid = member.gid = 0
                        with path.open("rb") as handle:
                            tar.addfile(member, handle)
            dockerfile = self._dockerfile(spec).encode("utf-8")
            info = tarfile.TarInfo("Dockerfile")
            info.size = len(dockerfile)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(dockerfile))
        context.seek(0)
        compile_log = self.last_build_log
        if compiled is not None:
            shutil.rmtree(compiled, ignore_errors=True)
        tag = f"ottv2-bot:{submission_id}"
        output = bytearray()
        try:
            _, stream = self.client.images.build(
                fileobj=context, custom_context=True, dockerfile="Dockerfile", tag=tag,
                rm=True, forcerm=True, pull=False, network_mode="none",
            )
            for record in stream:
                if isinstance(record, dict):
                    if record.get("error"):
                        text = str(record["error"])
                        if record.get("errorDetail", {}).get("code"):
                            text += f" (code {record['errorDetail']['code']})"
                        raise BotBuildError(text[:4096])
                    text = record.get("stream") or record.get("status") or ""
                    if text:
                        output.extend(str(text).encode("utf-8", "replace"))
                        if len(output) > MAX_BUILD_LOG_BYTES:
                            del output[MAX_BUILD_LOG_BYTES:]
            image = self.client.images.get(tag)
            self.last_build_log = (compile_log + bytes(output))[:MAX_BUILD_LOG_BYTES]
            # Local Docker image IDs are immutable and useful for a single-daemon dev setup.
            return str(image.id)
        except BotBuildError:
            self.last_build_log = (compile_log + bytes(output))[:MAX_BUILD_LOG_BYTES]
            raise
        except Exception as exc:
            detail = str(exc)
            if "exit code" in detail.lower() or "failed to solve" in detail.lower():
                raise BotBuildError(detail[:4096]) from exc
            raise InfrastructureError("Docker image build failed due to worker infrastructure") from exc

    def _compile(self, spec: BuildSpec, source_dir: Path) -> Path:
        command = {
            "cpp": ["sh", "-c", "g++ -std=c++20 -O2 -pipe -static main.cpp -o /tmp/main && cp /tmp/main /out/main"],
            "java": ["javac", "-d", "/out", "Main.java"],
        }[spec.language]
        output_dir = Path(tempfile.mkdtemp(prefix="compile-", dir=source_dir.parent))
        os.chmod(output_dir, 0o777)
        container = None
        try:
            container = self.client.containers.create(
                image=spec.builder_image,
                command=command,
                working_dir="/src",
                network_mode="none",
                mem_limit="512m",
                memswap_limit="512m",
                nano_cpus=1_000_000_000,
                pids_limit=16,
                read_only=True,
                tmpfs={"/tmp": "rw,noexec,nosuid,nodev,size=64m"},
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                user="10001:10001",
                ulimits=[{"name": "fsize", "soft": 16 * 1024 * 1024, "hard": 16 * 1024 * 1024}],
                volumes={
                    str(source_dir.resolve()): {"bind": "/src", "mode": "ro"},
                    str(output_dir.resolve()): {"bind": "/out", "mode": "rw"},
                },
                detach=True,
            )
            with self._active_build_lock:
                self._active_build_container = container
            container.start()
            result = container.wait(timeout=60)
            exit_code = result.get("StatusCode", -1)
            log = bytearray()
            for chunk in container.logs(stdout=True, stderr=True, stream=True, follow=False):
                room = MAX_BUILD_LOG_BYTES - len(log)
                if room > 0:
                    log.extend(chunk[:room])
            self.last_build_log = bytes(log)
            if exit_code != 0:
                raise BotBuildError(f"Compiler exited with status {exit_code}")
            return output_dir
        except BotBuildError:
            raise
        except Exception as exc:
            if "timeout" in str(exc).lower():
                raise BotBuildError("Build exceeded the 60 second limit") from exc
            raise InfrastructureError("Isolated compiler container failed") from exc
        finally:
            if container is not None:
                try:
                    container.kill()
                except Exception:
                    pass
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            with self._active_build_lock:
                self._active_build_container = None

    @staticmethod
    def _dockerfile(spec: BuildSpec) -> str:
        base = spec.runtime_image
        if spec.language == "python":
            return (
                f"FROM {base}\nWORKDIR /bot\nCOPY . /bot/\n"
                "USER 10001:10001\nENTRYPOINT [\"python\",\"-u\",\"/bot/main.py\"]\n"
            )
        if spec.language == "cpp":
            return (
                f"FROM {base}\nWORKDIR /bot\nCOPY compiled/main /bot/main\n"
                "USER 10001:10001\nENTRYPOINT [\"/bot/main\"]\n"
            )
        if spec.language == "java":
            return (
                f"FROM {base}\nWORKDIR /bot\nCOPY compiled/ /bot/\n"
                "USER 10001:10001\nENTRYPOINT [\"java\",\"-cp\",\"/bot\",\"Main\"]\n"
            )
        return (
            f"FROM {base}\nWORKDIR /bot\nCOPY . /bot/\n"
            "USER 10001:10001\nENTRYPOINT [\"node\",\"/bot/main.js\"]\n"
        )

    def _ensure_image(self, image: str) -> None:
        try:
            self.client.images.get(image)
        except Exception:
            if "@sha256:" not in image:
                raise InfrastructureError("Bot image is not available locally")
            self.client.images.pull(image)

    def start_bot(self, image: str, cpu: str) -> "DockerBot":
        try:
            self._ensure_image(image)
            container = self.client.containers.create(
                image=image,
                stdin_open=True,
                tty=False,
                detach=True,
                network_mode="none",
                mem_limit="512m",
                memswap_limit="512m",
                nano_cpus=1_000_000_000,
                cpuset_cpus=cpu,
                pids_limit=16,
                read_only=True,
                tmpfs={"/tmp": "rw,noexec,nosuid,nodev,size=64m"},
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                user="10001:10001",
                ulimits=[{"name": "fsize", "soft": 16 * 1024 * 1024, "hard": 16 * 1024 * 1024}],
            )
            return DockerBot(container)
        except Exception as exc:
            raise InfrastructureError("Could not create sandbox container") from exc


class DockerBot:
    """Drains Docker's multiplexed stdout/stderr stream independently in a reader thread."""

    def __init__(self, container: Any):
        self.container = container
        self.started_at_ns = 0
        self.stderr = bytearray()
        self.debug = bytearray()
        self._stdout_bytes = 0
        self._lines: queue.Queue[bytes | BaseException | None] = queue.Queue(maxsize=128)
        self._socket: socket.socket | None = None
        self._reader: threading.Thread | None = None
        self._closed = False
        self._error: BaseException | None = None
        try:
            sock = container.attach_socket(params={"stdin": 1, "stdout": 1, "stderr": 1, "stream": 1})
            self._socket = getattr(sock, "_sock", sock)
            self._socket.settimeout(None)
            self.started_at_ns = time.monotonic_ns()
            container.start()
            self._reader = threading.Thread(target=self._drain, name="runner-bot-io", daemon=True)
            self._reader.start()
        except Exception as exc:
            self.abort()
            raise InfrastructureError("Could not start sandbox container") from exc

    def _read_exact(self, count: int) -> bytes:
        assert self._socket is not None
        parts = bytearray()
        while len(parts) < count:
            piece = self._socket.recv(count - len(parts))
            if not piece:
                return bytes(parts)
            parts.extend(piece)
        return bytes(parts)

    def _queue_line(self, line: bytes) -> None:
        self._stdout_bytes += len(line) + 1
        if self._stdout_bytes > MAX_BOT_STDOUT_BYTES:
            self._error = _protocol_error("Bot stdout exceeded 1 MiB")
            return
        if line.startswith(b"#"):
            remaining = MAX_BOT_DEBUG_BYTES - len(self.debug)
            if remaining > 0:
                self.debug.extend(line[:remaining])
                if len(self.debug) < MAX_BOT_DEBUG_BYTES:
                    self.debug.extend(b"\n")
        try:
            self._lines.put_nowait(line)
        except queue.Full:
            self._error = _protocol_error("Bot produced too much unread protocol output")

    def _drain_stdout(self, chunk: bytes, pending: bytearray) -> None:
        pending.extend(chunk)
        while b"\n" in pending:
            line, _, tail = pending.partition(b"\n")
            pending[:] = tail
            if len(line) + 1 > MAX_BOT_LINE_BYTES:
                self._line_overflow()
                continue
            self._queue_line(line.rstrip(b"\r"))
        if len(pending) >= MAX_BOT_LINE_BYTES:
            self._line_overflow()
            pending.clear()

    def _line_overflow(self) -> None:
        self._error = _protocol_error("Bot protocol line exceeded 4096 bytes including LF")
        # Wake an engine already waiting for a line, even if the bot keeps stdout open.
        try:
            self._lines.put_nowait(self._error)
        except queue.Full:
            pass  # A queued item already wakes read_line, which checks _error.

    def _drain(self) -> None:
        pending = bytearray()
        try:
            while self._socket is not None:
                header = self._read_exact(8)
                if not header:
                    break
                if len(header) != 8:
                    raise OSError("Truncated Docker stream header")
                stream_id = header[0]
                size = struct.unpack(">I", header[4:8])[0]
                if size > MAX_BOT_STDOUT_BYTES + MAX_BOT_STDERR_BYTES + 4096:
                    raise OSError("Oversized Docker stream frame")
                data = self._read_exact(size)
                if len(data) != size:
                    raise OSError("Truncated Docker stream frame")
                if stream_id == 1:
                    self._drain_stdout(data, pending)
                elif stream_id == 2:
                    room = MAX_BOT_STDERR_BYTES - len(self.stderr)
                    if room > 0:
                        self.stderr.extend(data[:room])
                else:
                    raise OSError("Unexpected Docker stream channel")
        except Exception:
            if not self._closed:
                self._error = _infrastructure_error("Docker attach stream failed")
        finally:
            if pending:
                self._error = _protocol_error("Bot stdout ended before the line was terminated")
            try:
                self._lines.put_nowait(None)
            except queue.Full:
                self._error = _protocol_error("Bot output queue was full at EOF")

    async def send_line(self, text: str) -> None:
        if "\n" in text or "\r" in text:
            raise ValueError("send_line accepts one line")
        if self._socket is None or self._closed:
            raise EOFError
        try:
            await asyncio.to_thread(self._socket.sendall, (text + "\n").encode("utf-8"))
        except Exception as exc:
            raise EOFError from exc

    async def read_line(self, timeout_ms: int) -> str:
        if self._error:
            raise self._error
        try:
            line = await asyncio.to_thread(self._lines.get, True, max(timeout_ms, 0) / 1000)
        except queue.Empty as exc:
            raise TimeoutError from exc
        if line is None:
            if self._error:
                raise self._error
            raise EOFError
        if isinstance(line, BaseException):
            raise line
        if self._error:
            raise self._error
        try:
            return line.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise _protocol_error("Bot stdout was not valid UTF-8") from exc

    async def close(self) -> None:
        self.abort()
        if self._reader and self._reader.is_alive():
            await asyncio.to_thread(self._reader.join, 2)

    def abort(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._socket is not None:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._socket.close()
            except OSError:
                pass
        try:
            self.container.kill()
        except Exception:
            pass
        try:
            self.container.remove(force=True)
        except Exception:
            pass
