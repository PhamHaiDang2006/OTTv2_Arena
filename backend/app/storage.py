"""S3/MinIO access. Keys are object keys (architecture.md 5.3), never URLs."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.config import get_settings
from app.errors import ApiError


class StorageError(Exception):
    pass


def submission_source_key(submission_id: str) -> str:
    return f'submissions/{submission_id}/source.zip'


def build_log_key(submission_id: str) -> str:
    return f'builds/{submission_id}/build.log'


def replay_key(game_id: str) -> str:
    return f'replays/{game_id}.json.gz'


def log_prefix(game_id: str) -> str:
    return f'logs/{game_id}/'


STDERR_FILES = {'BLUE': 'blue.stderr.log', 'RED': 'red.stderr.log'}


class Storage:
    def __init__(self) -> None:
        settings = get_settings()
        config = Config(signature_version='s3v4', s3={'addressing_style': 'path'}, retries={'max_attempts': 3})
        common = dict(region_name=settings.s3_region, aws_access_key_id=settings.s3_access_key_id,
                      aws_secret_access_key=settings.s3_secret_access_key, config=config)
        self.bucket = settings.s3_bucket
        self.client = boto3.client('s3', endpoint_url=settings.s3_endpoint_url, **common)
        # Presigned URLs must use the browser-reachable endpoint, not a container hostname.
        self.public = boto3.client('s3', endpoint_url=settings.s3_public_endpoint_url or settings.s3_endpoint_url, **common)

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)

    def put(self, key: str, data: bytes, content_type: str = 'application/octet-stream') -> None:
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(str(exc)) from exc

    def head(self, key: str) -> dict[str, Any] | None:
        try:
            return self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response.get('Error', {}).get('Code') in ('404', 'NoSuchKey', 'NotFound'):
                return None
            raise StorageError(str(exc)) from exc
        except BotoCoreError as exc:
            raise StorageError(str(exc)) from exc

    def read(self, key: str, max_bytes: int | None = None) -> tuple[bytes, int]:
        """Return (prefix of at most max_bytes, full object size)."""
        try:
            kwargs: dict[str, Any] = {'Bucket': self.bucket, 'Key': key}
            if max_bytes is not None:
                kwargs['Range'] = f'bytes=0-{max_bytes - 1}'
            response = self.client.get_object(**kwargs)
            data = response['Body'].read()
            total = response.get('ContentLength', len(data))
            content_range = response.get('ContentRange')
            if content_range and '/' in content_range:
                total = int(content_range.rsplit('/', 1)[1])
            return data, total
        except ClientError as exc:
            code = exc.response.get('Error', {}).get('Code')
            if code == 'InvalidRange':
                return b'', 0
            if code in ('404', 'NoSuchKey', 'NotFound'):
                raise FileNotFoundError(key) from exc
            raise StorageError(str(exc)) from exc
        except BotoCoreError as exc:
            raise StorageError(str(exc)) from exc

    def copy(self, source: str, target: str) -> None:
        try:
            self.client.copy_object(Bucket=self.bucket, Key=target, CopySource={'Bucket': self.bucket, 'Key': source},
                                    MetadataDirective='COPY')
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(str(exc)) from exc

    def presign_get(self, key: str, ttl_seconds: int) -> str:
        return self.public.generate_presigned_url('get_object', Params={'Bucket': self.bucket, 'Key': key},
                                                  ExpiresIn=ttl_seconds)


@lru_cache
def get_storage() -> Storage:
    return Storage()


def unavailable(exc: Exception) -> ApiError:
    return ApiError(503, 'SERVICE_UNAVAILABLE', 'Kho lưu trữ tạm thời không sẵn sàng')
