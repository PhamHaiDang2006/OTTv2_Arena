"""Runtime settings. Variable names follow infra/.env.example; extra ones are backend-only."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra='ignore')

    database_url: str
    redis_url: str
    s3_endpoint_url: str | None = None
    s3_public_endpoint_url: str | None = None
    s3_bucket: str = 'ottv2'
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_region: str = 'us-east-1'
    jwt_secret: str
    worker_api_token: str
    frontend_origins: str = ''
    allow_development_tournaments: bool = False
    ruleset_id: str = 'dev-v1'

    # Backend-only settings (not yet in infra/.env.example).
    engine_version: str = '1.0.0'
    enabled_languages: str = 'python,cpp'
    cookie_secure: bool = True
    contracts_dir: Path = REPO_DIR / 'contracts'
    architecture_path: Path = REPO_DIR / 'architecture.md'
    replay_url_ttl_seconds: int = 300
    starter_kits_json: str = '[]'
    submission_rate_per_hour: int = 10
    login_rate_per_minute: int = 10
    registration_rate_per_hour: int = 5
    rq_build_timeout_seconds: int = 600
    rq_match_timeout_seconds: int = 1800

    @field_validator('ruleset_id')
    @classmethod
    def _known_ruleset(cls, value: str) -> str:
        if value != 'dev-v1':
            raise ValueError('Only ruleset dev-v1 exists in contract v1.0.0')
        return value

    @property
    def origins(self) -> list[str]:
        return [o.strip().rstrip('/') for o in self.frontend_origins.split(',') if o.strip()]

    @property
    def languages(self) -> list[str]:
        allowed = ('python', 'cpp', 'java', 'node')
        chosen = [x.strip() for x in self.enabled_languages.split(',') if x.strip()]
        return [x for x in allowed if x in chosen]

    @property
    def starter_kits(self) -> list[dict]:
        return json.loads(self.starter_kits_json)


@lru_cache
def get_settings() -> Settings:
    return Settings()
