from __future__ import annotations

import stat
import unicodedata
import zipfile
import re
from pathlib import Path, PurePosixPath

from .errors import BotBuildError

MAX_ARCHIVE_BYTES = 1 * 1024 * 1024
MAX_FILES = 50
MAX_FILE_BYTES = 1 * 1024 * 1024
MAX_TOTAL_BYTES = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {".py", ".cpp", ".h", ".hpp", ".java", ".js", ".json", ".txt", ".md"}
MAIN_FILES = {"python": "main.py", "cpp": "main.cpp", "java": "Main.java", "node": "main.js"}
ARCHIVE_EXTENSIONS = {".zip", ".gz", ".tgz", ".tar", ".7z", ".rar"}


def _safe_name(name: str) -> str:
    if not name or "\x00" in name or "\\" in name:
        raise BotBuildError("Archive contains an invalid path")
    normalized = unicodedata.normalize("NFC", name)
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise BotBuildError("Archive contains an absolute or traversing path")
    windows_devices = re.compile(r"(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$")
    for part in path.parts:
        if (
            ":" in part or part.startswith("~") or part.endswith((".", " "))
            or windows_devices.fullmatch(part)
        ):
            raise BotBuildError("Archive contains a platform-specific or reserved path")
    return path.as_posix()


def extract_source(archive_bytes: bytes, destination: Path, language: str) -> list[Path]:
    if len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise BotBuildError("Source ZIP exceeds 1 MiB")
    destination.mkdir(parents=True, exist_ok=True)
    try:
        archive = zipfile.ZipFile(__import__("io").BytesIO(archive_bytes))
    except (zipfile.BadZipFile, OSError) as exc:
        raise BotBuildError("Source is not a valid ZIP archive") from exc

    written: list[Path] = []
    seen: set[str] = set()
    files = 0
    total = 0
    try:
        with archive:
            for info in archive.infolist():
                path = _safe_name(info.filename.rstrip("/") if info.is_dir() else info.filename)
                collision_key = path.casefold()
                if collision_key in seen:
                    raise BotBuildError("Archive contains duplicate normalized paths")
                seen.add(collision_key)
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise BotBuildError("Symbolic links are not permitted in source ZIPs")
                if not info.is_dir() and mode and stat.S_IFMT(mode) not in {0, stat.S_IFREG}:
                    raise BotBuildError("Special filesystem entries are not permitted in source ZIPs")
                if info.is_dir():
                    (destination / path).mkdir(parents=True, exist_ok=True)
                    continue
                files += 1
                if files > MAX_FILES:
                    raise BotBuildError("Source ZIP contains more than 50 files")
                if info.file_size > MAX_FILE_BYTES:
                    raise BotBuildError("A source file exceeds 1 MiB")
                total += info.file_size
                if total > MAX_TOTAL_BYTES:
                    raise BotBuildError("Expanded source exceeds 5 MiB")
                suffix = Path(path).suffix.lower()
                if suffix in ARCHIVE_EXTENSIONS:
                    raise BotBuildError("Nested archives are not permitted")
                if suffix not in ALLOWED_EXTENSIONS:
                    raise BotBuildError(f"Unsupported source file extension: {suffix or '(none)'}")
                output = destination.joinpath(*PurePosixPath(path).parts)
                output.parent.mkdir(parents=True, exist_ok=True)
                actual_size = 0
                try:
                    with archive.open(info) as source, output.open("xb") as target:
                        while chunk := source.read(64 * 1024):
                            actual_size += len(chunk)
                            if actual_size > MAX_FILE_BYTES or total - info.file_size + actual_size > MAX_TOTAL_BYTES:
                                raise BotBuildError("Expanded source exceeds configured limits")
                            if b"\x00" in chunk:
                                raise BotBuildError("Binary source files are not permitted")
                            target.write(chunk)
                except (UnicodeDecodeError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
                    raise BotBuildError("Could not safely extract source ZIP") from exc
                # Source files must be text; decode incrementally in a bounded file.
                try:
                    output.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError) as exc:
                    raise BotBuildError("Source files must be valid UTF-8") from exc
                written.append(output)
    except (RuntimeError, zipfile.BadZipFile) as exc:
        raise BotBuildError("Source ZIP is corrupt") from exc

    main_file = MAIN_FILES[language]
    if not (destination / main_file).is_file():
        raise BotBuildError(f"ZIP must contain {main_file} at its root")
    return written
