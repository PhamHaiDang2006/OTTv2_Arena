from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from typing import Any

from .errors import JobValidationError

_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?$")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_KEY = re.compile(r"^(?!/)(?!.*\.\.)(?!.*\\)[a-zA-Z0-9_./-]+$")
_FEN = re.compile(r"^[BPKbpk1-9]+(?:/[BPKbpk1-9]+){8}$")
_LANGUAGES = {"python", "cpp", "java", "node"}
_CONFIG_FIELDS = {
    "engine_version", "ruleset_id", "map_id", "initial_fen", "players",
    "budget_ms", "init_ms", "grace_ms", "hard_timeout_extra_ms", "max_turns", "seed",
}
_PLAYER_FIELDS = {"team", "submission_id"}


def _object(value: Any, name: str, fields: set[str], required: set[str] | None = None) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise JobValidationError(f"{name} must be an object")
    required = fields if required is None else required
    if set(value) != fields:
        missing, extra = required - set(value), set(value) - fields
        if missing:
            raise JobValidationError(f"{name} missing required fields: {', '.join(sorted(missing))}")
        if extra:
            raise JobValidationError(f"{name} has unknown fields: {', '.join(sorted(extra))}")
        raise JobValidationError(f"{name} has an invalid shape")
    return value


def _uuid(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _UUID.fullmatch(value):
        raise JobValidationError(f"{name} must be a UUID string")
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise JobValidationError(f"{name} must be a UUID string") from exc
    return value


def _version(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        raise JobValidationError(f"{name} is not a semantic version")
    return value


def _key(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _KEY.fullmatch(value):
        raise JobValidationError(f"{name} is not a safe object key")
    return value


def _players(value: Any, name: str) -> Mapping[str, Any]:
    players = _object(value, name, {"BLUE", "RED"})
    for side in ("BLUE", "RED"):
        player = _object(players[side], f"{name}.{side}", _PLAYER_FIELDS)
        if not isinstance(player["team"], str) or not player["team"]:
            raise JobValidationError(f"{name}.{side}.team must be a non-empty string")
        _uuid(player["submission_id"], f"{name}.{side}.submission_id")
    return players


def _config(value: Any) -> Mapping[str, Any]:
    config = _object(value, "config", _CONFIG_FIELDS)
    _version(config["engine_version"], "config.engine_version")
    if config["ruleset_id"] != "dev-v1" or config["map_id"] != "standard":
        raise JobValidationError("config ruleset_id/map_id are not supported by contract v1")
    if not isinstance(config["initial_fen"], str) or not _FEN.fullmatch(config["initial_fen"]):
        raise JobValidationError("config.initial_fen has an invalid shape")
    _players(config["players"], "config.players")
    constants = {
        "budget_ms": 60000, "init_ms": 10000, "grace_ms": 50,
        "hard_timeout_extra_ms": 1000, "max_turns": 300,
    }
    for field, expected in constants.items():
        if type(config[field]) is not int or config[field] != expected:
            raise JobValidationError(f"config.{field} must equal {expected}")
    if type(config["seed"]) is not int or config["seed"] < 0:
        raise JobValidationError("config.seed must be a non-negative integer")
    return config


def validate_build_job(payload: Any) -> dict[str, Any]:
    fields = {"schema_version", "job_id", "submission_id", "language", "source_key", "source_sha256", "engine_version"}
    job = dict(_object(payload, "build job", fields))
    if type(job["schema_version"]) is not int or job["schema_version"] != 1:
        raise JobValidationError("build job schema_version must be 1")
    _uuid(job["job_id"], "job_id")
    _uuid(job["submission_id"], "submission_id")
    if not isinstance(job["language"], str) or job["language"] not in _LANGUAGES:
        raise JobValidationError("language must be python, cpp, java, or node")
    _key(job["source_key"], "source_key")
    if not isinstance(job["source_sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", job["source_sha256"]):
        raise JobValidationError("source_sha256 must be a lowercase SHA-256 hex digest")
    _version(job["engine_version"], "engine_version")
    return job


def validate_match_job(payload: Any) -> dict[str, Any]:
    fields = {
        "schema_version", "job_id", "game_id", "attempt", "blue_image", "red_image",
        "map_id", "engine_version", "players", "config",
    }
    job = dict(_object(payload, "match job", fields))
    if type(job["schema_version"]) is not int or job["schema_version"] != 1:
        raise JobValidationError("match job schema_version must be 1")
    _uuid(job["job_id"], "job_id")
    _uuid(job["game_id"], "game_id")
    if type(job["attempt"]) is not int or job["attempt"] < 1:
        raise JobValidationError("attempt must be a positive integer")
    for name in ("blue_image", "red_image"):
        if not isinstance(job[name], str) or not job[name]:
            raise JobValidationError(f"{name} must be a non-empty string")
    if job["map_id"] != "standard":
        raise JobValidationError("map_id must be standard")
    _version(job["engine_version"], "engine_version")
    players = _players(job["players"], "players")
    config = _config(job["config"])
    for name in ("engine_version", "map_id", "players"):
        if job[name] != config[name]:
            raise JobValidationError(f"{name} must match config.{name}")
    if players != config["players"]:
        raise JobValidationError("players must match config.players")
    return job
