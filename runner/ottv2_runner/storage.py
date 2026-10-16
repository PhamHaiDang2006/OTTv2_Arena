from __future__ import annotations

import hashlib
import json
import gzip
from typing import Any, Protocol

from .errors import InfrastructureError


class ObjectStore(Protocol):
    def get(self, key: str) -> bytes: ...
    def put_immutable(
        self, key: str, data: bytes, content_type: str, content_encoding: str | None = None
    ) -> str: ...


class S3ObjectStore:
    def __init__(self, client: Any, bucket: str):
        self.client = client
        self.bucket = bucket

    def get(self, key: str) -> bytes:
        try:
            body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"]
            try:
                data = body.read(1024 * 1024 + 1)
            finally:
                body.close()
            if len(data) > 1024 * 1024:
                from .errors import BotBuildError
                raise BotBuildError("Source ZIP exceeds 1 MiB")
            return data
        except Exception as exc:
            from .errors import BotBuildError
            if isinstance(exc, BotBuildError):
                raise
            raise InfrastructureError("Could not download object from S3-compatible storage") from exc

    def put_immutable(
        self, key: str, data: bytes, content_type: str, content_encoding: str | None = None
    ) -> str:
        try:
            # Conditional creation prevents replacement of any existing staging object.
            parameters = {
                "Bucket": self.bucket, "Key": key, "Body": data,
                "ContentType": content_type, "IfNoneMatch": "*",
            }
            if content_encoding:
                parameters["ContentEncoding"] = content_encoding
            self.client.put_object(**parameters)
            return key
        except Exception as exc:
            raise InfrastructureError("Could not write immutable staging object") from exc


def staging_key(kind: str, resource_id: str, job_id: str, lease_token: str, filename: str) -> str:
    return f"staging/{kind}/{resource_id}/{job_id}/{lease_token}/{filename}"


def build_log_key(store: ObjectStore, key: str, data: bytes) -> str:
    return store.put_immutable(key, data[: 1024 * 1024], "text/plain; charset=utf-8")


def game_artifacts(store: ObjectStore, game_id: str, job_id: str, lease_token: str, replay: dict[str, Any], logs: dict[str, bytes]) -> tuple[str, str]:
    replay_key = staging_key("games", game_id, job_id, lease_token, "replay.json.gz")
    compressed = gzip.compress(json.dumps(replay, separators=(",", ":"), ensure_ascii=False).encode("utf-8"), mtime=0)
    store.put_immutable(replay_key, compressed, "application/json", content_encoding="gzip")
    log_keys: list[str] = []
    filenames = {
        "blue": "blue.stderr.log",
        "red": "red.stderr.log",
        "blue_debug": "blue.debug.log",
        "red_debug": "red.debug.log",
    }
    for name, filename in filenames.items():
        key = staging_key("games", game_id, job_id, lease_token, filename)
        store.put_immutable(key, logs.get(name, b"")[: 1024 * 1024], "text/plain; charset=utf-8")
        log_keys.append(key)
    # A slash-terminated key identifies the staged group without inventing a manifest protocol.
    log_group = log_keys[0].rsplit("/", 1)[0] + "/"
    return replay_key, log_group


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
