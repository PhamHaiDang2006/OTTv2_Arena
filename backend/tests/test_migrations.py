"""Migrations: head matches the models (no autogenerate drift) and a full downgrade/upgrade round-trips."""
from __future__ import annotations

import os

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.cli import BACKEND_DIR


def config() -> Config:
    cfg = Config(os.path.join(BACKEND_DIR, 'alembic.ini'))
    cfg.attributes['configure_logging'] = False
    return cfg


def test_single_head():
    assert len(ScriptDirectory.from_config(config()).get_heads()) == 1


def test_models_match_head_and_round_trip(database):
    command.check(config())  # raises if models differ from the migrated schema
    command.downgrade(config(), 'base')
    command.upgrade(config(), 'head')
    command.check(config())
