"""Test harness on real PostgreSQL and Redis (DATABASE_URL / REDIS_URL); S3 is mocked with moto.

Safety: the database name must contain "test" and Redis must not be DB 0, because every test truncates all
tables and flushes the Redis database.
"""
from __future__ import annotations

import os
import re
import uuid
from urllib.parse import urlsplit

import pytest

DATABASE_URL = os.environ.get('DATABASE_URL')
REDIS_URL = os.environ.get('REDIS_URL')
if not DATABASE_URL or not REDIS_URL:
    raise pytest.UsageError('Set DATABASE_URL and REDIS_URL to a disposable PostgreSQL 16 / Redis 7 (see README).')
if 'test' not in urlsplit(DATABASE_URL).path:
    raise pytest.UsageError('DATABASE_URL database name must contain "test" (tests truncate every table).')
if urlsplit(REDIS_URL).path in ('', '/', '/0'):
    raise pytest.UsageError('REDIS_URL must select a non-zero DB, e.g. redis://localhost:6379/15 (tests flush it).')

ORIGIN = 'http://localhost:5173'
os.environ.update({
    'JWT_SECRET': 'test-secret-test-secret-test-secret-0001', 'WORKER_API_TOKEN': 'test-worker-token',
    'FRONTEND_ORIGINS': f'{ORIGIN},http://localhost:5174', 'COOKIE_SECURE': 'false',
    'ALLOW_DEVELOPMENT_TOURNAMENTS': 'true', 'S3_BUCKET': 'ottv2-test', 'S3_ACCESS_KEY_ID': 'testing',
    'S3_SECRET_ACCESS_KEY': 'testing', 'AWS_ACCESS_KEY_ID': 'testing', 'AWS_SECRET_ACCESS_KEY': 'testing',
    'LOGIN_RATE_PER_MINUTE': '1000', 'SUBMISSION_RATE_PER_HOUR': '1000',
})
for name in ('S3_ENDPOINT_URL', 'S3_PUBLIC_ENDPOINT_URL'):
    os.environ.pop(name, None)  # moto intercepts the default AWS endpoint only

from fastapi.testclient import TestClient  # noqa: E402
from moto import mock_aws  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import contract  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import get_engine  # noqa: E402
from app.queue import get_redis  # noqa: E402
from app.storage import get_storage  # noqa: E402


@pytest.fixture(scope='session', autouse=True)
def database():
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text('DROP SCHEMA public CASCADE'))
        conn.execute(text('CREATE SCHEMA public'))
    from app.cli import migrate
    migrate()
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_state(database):
    with database.begin() as conn:
        tables = [r[0] for r in conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'"))]
        conn.execute(text(f'TRUNCATE {", ".join(tables)} RESTART IDENTITY CASCADE'))
    get_redis().flushdb()
    settings = get_settings()
    settings.allow_development_tournaments = True
    with mock_aws():
        get_storage.cache_clear()
        get_storage().ensure_bucket()
        yield
        get_storage.cache_clear()


_OPS = [(op['method'].upper(), re.compile('^/api/v1' + re.sub(r'\{\w+\}', r'[^/]+', op['path']) + '$'), op)
        for op in contract.operations()]
DOCUMENTED_ERRORS = {400, 401, 403, 404, 409, 413, 422, 429, 500, 503}


def operation_for(method: str, path: str) -> dict | None:
    for op_method, pattern, op in _OPS:
        if op_method == method.upper() and pattern.match(path):
            return op
    return None


class ContractClient:
    """TestClient wrapper: every response is validated against contracts/ (success schema or Error)."""

    def __init__(self, client: TestClient):
        self.raw = client

    def request(self, method: str, url: str, *, idem: bool | str = True, **kwargs):
        headers = dict(kwargs.pop('headers', None) or {})
        if idem and method.upper() not in ('GET', 'HEAD') and 'Idempotency-Key' not in headers:
            headers['Idempotency-Key'] = idem if isinstance(idem, str) else str(uuid.uuid4())
        response = self.raw.request(method, url, headers=headers, **kwargs)
        path = urlsplit(url).path
        op = operation_for(method, path)
        if response.status_code >= 400:
            assert response.status_code in DOCUMENTED_ERRORS, (response.status_code, response.text)
            problems = contract.errors('Error', response.json())
            assert not problems, (path, problems, response.text)
        elif op is not None:
            assert response.status_code == op['status'], (op['operationId'], response.status_code, response.text)
            if op['response']:
                problems = contract.errors(op['response'], response.json())
                assert not problems, (op['operationId'], problems, response.json())
            else:
                assert response.content == b''
        return response

    def get(self, url, **kw):
        return self.request('GET', url, **kw)

    def post(self, url, **kw):
        return self.request('POST', url, **kw)

    def put(self, url, **kw):
        return self.request('PUT', url, **kw)

    def patch(self, url, **kw):
        return self.request('PATCH', url, **kw)


@pytest.fixture
def raw_client():
    from app.main import app
    with TestClient(app, base_url='http://testserver') as client:
        yield client


@pytest.fixture
def api(raw_client):
    return ContractClient(raw_client)
