"""Public endpoints: health, capabilities, docs, published announcements."""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import contract
from app import serializers as ser
from app.config import get_settings
from app.db import get_db
from app.deps import OpInput, contract_input
from app.models import Announcement
from app.queue import get_redis

router = APIRouter()
log = logging.getLogger('ottv2.health')


@router.get('/health')
def health(db: Session = Depends(get_db)):
    status = 'ok'
    try:
        db.execute(text('SELECT 1'))
    except Exception as exc:  # noqa: BLE001 - report degraded instead of failing liveness
        log.warning('Health: database unavailable: %s', exc)
        status = 'degraded'
    try:
        get_redis().ping()
    except Exception as exc:  # noqa: BLE001
        log.warning('Health: redis unavailable: %s', exc)
        status = 'degraded'
    return {'status': status, 'contract_version': contract.CONTRACT_VERSION}


def tournament_enabled() -> bool:
    """Development rulesets may only run tournaments when explicitly allowed (never in production)."""
    return contract.RULESET_STATUS != 'development' or get_settings().allow_development_tournaments


@router.get('/capabilities')
def capabilities():
    return {'contract_version': contract.CONTRACT_VERSION, 'languages': get_settings().languages,
            'max_upload_bytes': 1048576, 'max_files': 50, 'ruleset_id': get_settings().ruleset_id,
            'ruleset_status': contract.RULESET_STATUS, 'tournament_enabled': tournament_enabled()}


def _protocol_section(markdown: str) -> str:
    match = re.search(r'^## 4\. .*?(?=^## \d+\. )', markdown, flags=re.M | re.S)
    return match.group(0).strip() if match else ''


@router.get('/docs')
def docs():
    settings = get_settings()
    rules = (contract.contracts_dir() / 'rules.md').read_text(encoding='utf-8')
    try:
        protocol = _protocol_section(settings.architecture_path.read_text(encoding='utf-8'))
    except OSError:
        protocol = ''
    return {'rules_markdown': rules, 'protocol_markdown': protocol, 'starter_kits': settings.starter_kits}


@router.get('/announcements')
def list_announcements(inp: OpInput = Depends(contract_input('listAnnouncements')), db: Session = Depends(get_db)):
    query = (select(Announcement).where(Announcement.published_at.is_not(None))
             .order_by(Announcement.created_at.desc(), Announcement.id))
    return ser.page(db, query, inp.params['page'], inp.params['page_size'],
                    lambda rows: [ser.announcement(r) for r in rows])
