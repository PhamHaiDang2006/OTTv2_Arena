"""Request plumbing shared by routers: authentication, contract-driven parameter/body validation."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from fastapi import Depends, Request
from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import contract
from app.db import get_db
from app.errors import ApiError, invalid
from app.models import TeamMember, User
from app.security import TokenError, decode_access_token, worker_token_ok


@dataclass
class Actor:
    user: User
    team_id: uuid.UUID | None

    @property
    def id(self) -> uuid.UUID:
        return self.user.id

    @property
    def is_admin(self) -> bool:
        return self.user.role == 'admin'


def bearer(request: Request) -> str | None:
    header = request.headers.get('Authorization', '')
    scheme, _, token = header.partition(' ')
    if scheme.lower() != 'bearer' or not token.strip():
        return None
    return token.strip()


def load_actor(db: Session, user_id: uuid.UUID) -> Actor | None:
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    team_id = db.scalar(select(TeamMember.team_id).where(TeamMember.user_id == user.id))
    return Actor(user=user, team_id=team_id)


def current_actor(request: Request, db: Session = Depends(get_db)) -> Actor:
    token = bearer(request)
    if token is None:
        raise ApiError(401, 'UNAUTHORIZED')
    try:
        claims = decode_access_token(token)
    except TokenError as exc:
        raise ApiError(401, 'UNAUTHORIZED', 'Phiên đăng nhập đã hết hạn' if exc.expired else None,
                       {'reason': 'token_expired' if exc.expired else 'token_invalid'}) from exc
    actor = load_actor(db, uuid.UUID(claims['sub']))
    if actor is None:
        raise ApiError(401, 'UNAUTHORIZED')
    request.state.actor_id = actor.id
    return actor


def require_member(actor: Actor = Depends(current_actor)) -> Actor:
    return actor  # x-role=member: member, captain and admin pass the route check


def require_captain(actor: Actor = Depends(current_actor)) -> Actor:
    if actor.user.role not in ('captain', 'admin'):
        raise ApiError(403, 'FORBIDDEN', 'Chỉ đội trưởng được thực hiện thao tác này')
    return actor


def require_admin(actor: Actor = Depends(current_actor)) -> Actor:
    if actor.user.role != 'admin':
        raise ApiError(403, 'FORBIDDEN')
    return actor


def require_team(actor: Actor) -> uuid.UUID:
    """Team-owned member endpoints act only for the caller's own team (admins have none)."""
    if actor.team_id is None:
        raise ApiError(403, 'FORBIDDEN', 'Tài khoản không thuộc đội nào')
    return actor.team_id


def require_worker(request: Request) -> None:
    token = bearer(request)
    if token is None or not worker_token_ok(token):
        raise ApiError(401, 'UNAUTHORIZED', 'Thiếu hoặc sai token worker')


def uuid_header(request: Request, name: str) -> uuid.UUID:
    value = request.headers.get(name)
    if value is None:
        raise invalid(f'Thiếu header {name}', field=name)
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise invalid(f'Header {name} phải là UUID', field=name) from exc


@lru_cache
def _openapi() -> dict:
    return contract.read_json('openapi.yaml')  # JSON syntax, valid YAML 1.2


@lru_cache
def _operation(operation_id: str) -> tuple[dict, dict]:
    op = next(o for o in contract.operations() if o['operationId'] == operation_id)
    return op, _openapi()['paths'][op['path']][op['method']]


@lru_cache
def _param_validator(schema_json: str) -> Draft202012Validator:
    schema = json.loads(schema_json.replace('#/components/schemas/', '#/$defs/'))
    common = contract.read_json('schemas/common.schema.json')
    return Draft202012Validator({'$defs': common['$defs'], **schema}, format_checker=FormatChecker())


@dataclass
class OpInput:
    params: dict[str, Any] = field(default_factory=dict)
    body: Any = None


def contract_input(operation_id: str):
    """Validate path/query parameters and the JSON body exactly as the contract operation declares them."""
    op, spec = _operation(operation_id)

    async def dependency(request: Request) -> OpInput:
        params: dict[str, Any] = {}
        for p in spec['parameters']:
            if p['in'] == 'header':
                continue
            name, schema = p['name'], p['schema']
            raw = request.path_params.get(name) if p['in'] == 'path' else request.query_params.get(name)
            if raw is None:
                if p.get('required'):
                    raise invalid(f'Thiếu tham số {name}', field=name)
                params[name] = schema.get('default')
                continue
            value: Any = raw
            if schema.get('type') == 'integer':
                try:
                    value = int(raw)
                except ValueError as exc:
                    raise invalid(f'Tham số {name} phải là số nguyên', field=name) from exc
            if list(_param_validator(json.dumps(schema, sort_keys=True)).iter_errors(value)):
                raise invalid(f'Tham số {name} không hợp lệ', field=name)
            params[name] = uuid.UUID(value) if schema.get('format') == 'uuid' else value
        body = None
        if op['request'] and not op['multipart']:
            if not request.headers.get('content-type', '').split(';')[0].strip() == 'application/json':
                raise invalid('Chỉ nhận Content-Type application/json')
            raw_body = await request.body()
            try:
                body = json.loads(raw_body)
            except (ValueError, UnicodeDecodeError) as exc:
                raise invalid('JSON không hợp lệ') from exc
            problems = contract.errors(op['request'], body)
            if problems:
                raise invalid(errors=problems[:20])
        return OpInput(params=params, body=body)

    return dependency


def page_window(params: dict[str, Any]) -> tuple[int, int]:
    return params['page'], params['page_size']
