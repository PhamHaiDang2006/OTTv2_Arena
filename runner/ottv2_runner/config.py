from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    api_base_url: str
    worker_token: str
    redis_url: str
    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str
    outbox_dir: Path
    worker_id: str
    callback_timeout_seconds: float = 10.0
    callback_backoff_seconds: tuple[float, ...] = (1, 2, 4, 8, 16, 30)
    enable_java: bool = False
    enable_node: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        def required(name: str) -> str:
            value = os.environ.get(name, "").strip()
            if not value:
                raise ValueError(f"Required runner setting {name} is missing")
            return value

        api_base_url = required("INTERNAL_API_BASE_URL").rstrip("/")
        if not api_base_url.endswith("/api/v1"):
            raise ValueError("INTERNAL_API_BASE_URL must include the /api/v1 prefix")
        return cls(
            api_base_url=api_base_url,
            worker_token=required("WORKER_API_TOKEN"),
            redis_url=required("REDIS_URL"),
            s3_endpoint_url=required("S3_ENDPOINT_URL"),
            s3_access_key=required("S3_ACCESS_KEY_ID"),
            s3_secret_key=required("S3_SECRET_ACCESS_KEY"),
            s3_bucket=required("S3_BUCKET"),
            outbox_dir=Path(os.environ.get("RUNNER_OUTBOX_DIR", "./runner-outbox")),
            worker_id=os.environ.get("RUNNER_WORKER_ID", socket.gethostname()),
            enable_java=os.environ.get("RUNNER_ENABLE_JAVA", "false").lower() == "true",
            enable_node=os.environ.get("RUNNER_ENABLE_NODE", "false").lower() == "true",
        )
