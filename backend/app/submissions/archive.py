"""Source ZIP validation (contracts/behavior.md "Submission, build và giới hạn").

Limits: ZIP <= 1 MiB, <= 50 files, <= 5 MiB uncompressed in total, <= 1 MiB per file; UTF-8 text only with an
allow-listed extension; no absolute paths, '..', symlinks, nested archives or duplicate paths; the language's
main file must sit at the ZIP root. Paths must also match the contract `key` pattern because SourceTree returns
them verbatim.
"""
from __future__ import annotations

import io
import re
import stat
import unicodedata
import zipfile
from typing import Any

from app.errors import ApiError

MAX_ZIP_BYTES = 1024 * 1024
MAX_FILES = 50
MAX_TOTAL_BYTES = 5 * 1024 * 1024
MAX_FILE_BYTES = 1024 * 1024
MAIN_FILES = {'python': 'main.py', 'cpp': 'main.cpp', 'java': 'Main.java', 'node': 'main.js'}
EXTENSION_LANGUAGE = {'.py': 'python', '.cpp': 'cpp', '.h': 'cpp', '.hpp': 'cpp', '.java': 'java', '.js': 'node',
                      '.json': 'json', '.txt': 'text', '.md': 'markdown'}
KEY_PATTERN = re.compile(r'^(?!/)(?!.*\.\.)(?!.*\\)[a-zA-Z0-9_./-]+$')
ARCHIVE_MAGIC = (b'PK\x03\x04', b'PK\x05\x06', b'\x1f\x8b', b'BZh', b'\xfd7zXZ', b'7z\xbc\xaf', b'Rar!', b'ustar')


def _reject(reason: str, message: str, path: str | None = None, status: int = 422) -> ApiError:
    details: dict[str, Any] = {'reason': reason}
    if path is not None:
        details['path'] = path[:300]
    code = 'PAYLOAD_TOO_LARGE' if status == 413 else 'INVALID_REQUEST'
    return ApiError(status, code, message, details)


def file_language(path: str) -> str:
    suffix = path[path.rfind('.'):].lower() if '.' in path.rsplit('/', 1)[-1] else ''
    return EXTENSION_LANGUAGE.get(suffix, 'text')


def _check_path(name: str) -> str:
    if name.startswith('/') or '\\' in name or re.match(r'^[A-Za-z]:', name):
        raise _reject('absolute_path', 'Không chấp nhận đường dẫn tuyệt đối', name)
    parts = name.split('/')
    if any(p == '..' for p in parts):
        raise _reject('path_traversal', 'Không chấp nhận đường dẫn chứa ..', name)
    if any(p in ('', '.') for p in parts):
        raise _reject('invalid_path', 'Đường dẫn tệp không hợp lệ', name)
    if not KEY_PATTERN.match(name):
        raise _reject('invalid_path', 'Tên tệp chỉ dùng chữ Latin không dấu, số, _ . / -', name)
    return name


def inspect(data: bytes, language: str) -> list[dict[str, Any]]:
    """Return the source manifest [{path, size_bytes, language}] or raise ApiError."""
    if len(data) > MAX_ZIP_BYTES:
        raise _reject('zip_too_large', 'Tệp ZIP vượt quá 1 MiB', status=413)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        infos = archive.infolist()
    except (zipfile.BadZipFile, ValueError, OSError) as exc:
        raise _reject('invalid_zip', 'Tệp tải lên không phải ZIP hợp lệ') from exc
    manifest: list[dict[str, Any]] = []
    seen: set[str] = set()
    total = 0
    for info in infos:
        name = info.filename
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise _reject('symlink', 'ZIP không được chứa symlink', name)
        if info.flag_bits & 0x1:
            raise _reject('encrypted', 'ZIP không được mã hóa', name)
        if info.is_dir():
            _check_path(name.rstrip('/'))
            continue
        path = _check_path(name)
        normalized = unicodedata.normalize('NFC', path).casefold()
        if normalized in seen:
            raise _reject('duplicate_path', 'ZIP chứa đường dẫn trùng nhau', name)
        seen.add(normalized)
        suffix = path[path.rfind('.'):].lower() if '.' in path.rsplit('/', 1)[-1] else ''
        if suffix not in EXTENSION_LANGUAGE:
            raise _reject('extension_not_allowed', 'Phần mở rộng tệp không được hỗ trợ', name)
        if len(manifest) + 1 > MAX_FILES:
            raise _reject('too_many_files', 'ZIP có quá 50 tệp')
        if info.file_size > MAX_FILE_BYTES:
            raise _reject('file_too_large', 'Một tệp vượt quá 1 MiB', name, status=413)
        try:
            with archive.open(info) as handle:
                content = handle.read(MAX_FILE_BYTES + 1)
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError, EOFError) as exc:
            raise _reject('invalid_zip', 'Không giải nén được tệp trong ZIP', name) from exc
        if len(content) > MAX_FILE_BYTES:
            raise _reject('file_too_large', 'Một tệp vượt quá 1 MiB', name, status=413)
        total += len(content)
        if total > MAX_TOTAL_BYTES:
            raise _reject('total_too_large', 'Tổng dung lượng giải nén vượt quá 5 MiB', status=413)
        if content.startswith(ARCHIVE_MAGIC) or b'\x00' in content:
            raise _reject('binary_file', 'ZIP không được chứa tệp nhị phân hoặc archive lồng', name)
        try:
            content.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise _reject('not_utf8', 'Tệp nguồn phải là văn bản UTF-8', name) from exc
        manifest.append({'path': path, 'size_bytes': len(content), 'language': file_language(path)})
    main = MAIN_FILES[language]
    if not any(entry['path'] == main for entry in manifest):
        raise _reject('main_file_missing', f'Thiếu tệp chính {main} ở gốc ZIP', main)
    return sorted(manifest, key=lambda entry: entry['path'])


def read_file(data: bytes, path: str, limit: int) -> tuple[str, bool]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        with archive.open(path) as handle:
            content = handle.read(limit + 1)
    truncated = len(content) > limit
    return content[:limit].decode('utf-8', errors='replace'), truncated
