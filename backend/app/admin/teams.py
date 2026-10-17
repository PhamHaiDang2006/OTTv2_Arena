"""Team administration, including all-or-nothing CSV import."""
from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import audit
from app.errors import conflict
from app.models import Group, GroupTeam, Team, TeamMember, Tournament, User

SLUG = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
CSV_HEADER = ['name', 'slug', 'captain_email', 'seed']


@dataclass
class TeamSpec:
    name: str
    slug: str
    captain_email: str
    seed: int | None


def _captain_problem(db: Session, email: str) -> str | None:
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None:
        return None
    if user.role == 'admin':
        return 'captain_is_admin'
    if db.scalar(select(TeamMember.team_id).where(TeamMember.user_id == user.id)) is not None:
        return 'captain_has_team'
    return None


def create_team(db: Session, actor_id: uuid.UUID, spec: TeamSpec, audit_action: str = 'team.create') -> Team:
    email = spec.captain_email.strip().lower()
    if db.scalar(select(Team.id).where(Team.slug == spec.slug)) is not None:
        raise conflict(message='Slug đã được dùng', reason='slug_taken')
    if spec.seed is not None and db.scalar(select(Team.id).where(Team.seed == spec.seed)) is not None:
        raise conflict(message='Hạt giống đã được dùng', reason='seed_taken')
    problem = _captain_problem(db, email)
    if problem:
        raise conflict(message='Email đội trưởng đã thuộc đội khác hoặc là admin', reason=problem)
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None:
        # No password is set through the API; accounts are activated with `app.cli set-password`.
        user = User(email=email, role='captain', password_hash=None, is_active=True)
        db.add(user)
    else:
        user.role = 'captain'
    team = Team(name=spec.name.strip(), slug=spec.slug, seed=spec.seed, status='pending', is_locked=False)
    db.add(team)
    db.flush()
    db.add(TeamMember(team_id=team.id, user_id=user.id))
    audit(db, actor_id, audit_action, 'team', team.id,
          {'name': team.name, 'slug': team.slug, 'captain_email': email, 'seed': team.seed})
    db.flush()
    return team


def _seed_locked(db: Session, team_id: uuid.UUID) -> bool:
    return db.scalar(
        select(Tournament.id).join(Group, Group.tournament_id == Tournament.id)
        .join(GroupTeam, GroupTeam.group_id == Group.id)
        .where(GroupTeam.team_id == team_id, Tournament.draw_locked, Tournament.status != 'finished').limit(1)
    ) is not None


def update_team(db: Session, actor_id: uuid.UUID, team: Team, body: dict[str, Any]) -> Team:
    fields = {k: v for k, v in body.items() if k != 'reason'}
    before = {k: getattr(team, k) for k in fields}
    if 'name' in fields and not fields['name'].strip():
        from app.errors import invalid
        raise invalid('Tên đội không được để trống', field='name')
    if 'seed' in fields and fields['seed'] != team.seed:
        if _seed_locked(db, team.id):
            raise conflict(message='Không đổi hạt giống sau khi đã chốt bốc thăm', reason='draw_locked')
        if fields['seed'] is not None and db.scalar(
                select(Team.id).where(Team.seed == fields['seed'], Team.id != team.id)) is not None:
            raise conflict(message='Hạt giống đã được dùng', reason='seed_taken')
    for key, value in fields.items():
        setattr(team, key, value.strip() if key == 'name' else value)
    audit(db, actor_id, 'team.update', 'team', team.id, {'reason': body['reason'], 'before': before, 'after': fields})
    db.flush()
    return team


def parse_import(db: Session, text: str) -> tuple[list[TeamSpec], list[dict[str, Any]]]:
    """Validate the whole CSV first; rows are numbered with the header as row 1."""
    errors: list[dict[str, Any]] = []
    rows = list(csv.reader(io.StringIO(text.lstrip('﻿'))))
    if not rows or [c.strip() for c in rows[0]] != CSV_HEADER:
        return [], [{'row': 1, 'code': 'INVALID_HEADER', 'message': 'Dòng tiêu đề phải là name,slug,captain_email,seed'}]
    specs: list[TeamSpec] = []
    seen_slug: dict[str, int] = {}
    seen_email: dict[str, int] = {}
    seen_seed: dict[int, int] = {}

    def err(row: int, code: str, message: str) -> None:
        errors.append({'row': row, 'code': code, 'message': message})

    for number, cells in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in cells):
            continue
        if len(cells) != 4:
            err(number, 'INVALID_COLUMNS', 'Mỗi dòng phải có đúng 4 cột')
            continue
        name, slug, email, seed_text = (c.strip() for c in cells)
        email = email.lower()
        ok = True
        if not 1 <= len(name) <= 100:
            err(number, 'INVALID_NAME', 'Tên đội dài 1–100 ký tự')
            ok = False
        if not SLUG.match(slug) or len(slug) > 100:
            err(number, 'INVALID_SLUG', 'Slug chỉ gồm a-z, 0-9 và dấu - giữa các phần')
            ok = False
        elif slug in seen_slug:
            err(number, 'DUPLICATE_SLUG', f'Slug trùng với dòng {seen_slug[slug]}')
            ok = False
        elif db.scalar(select(Team.id).where(Team.slug == slug)) is not None:
            err(number, 'SLUG_TAKEN', 'Slug đã tồn tại')
            ok = False
        if not EMAIL.match(email):
            err(number, 'INVALID_EMAIL', 'Email đội trưởng không hợp lệ')
            ok = False
        elif email in seen_email:
            err(number, 'DUPLICATE_EMAIL', f'Email trùng với dòng {seen_email[email]}')
            ok = False
        elif _captain_problem(db, email):
            err(number, 'EMAIL_TAKEN', 'Email đã thuộc đội khác hoặc là admin')
            ok = False
        seed: int | None = None
        if seed_text:
            if not seed_text.isdigit() or int(seed_text) < 1:
                err(number, 'INVALID_SEED', 'Hạt giống phải là số nguyên dương hoặc để trống')
                ok = False
            else:
                seed = int(seed_text)
                if seed in seen_seed:
                    err(number, 'DUPLICATE_SEED', f'Hạt giống trùng với dòng {seen_seed[seed]}')
                    ok = False
                elif db.scalar(select(Team.id).where(Team.seed == seed)) is not None:
                    err(number, 'SEED_TAKEN', 'Hạt giống đã được dùng')
                    ok = False
        seen_slug.setdefault(slug, number)
        seen_email.setdefault(email, number)
        if seed is not None:
            seen_seed.setdefault(seed, number)
        if ok:
            specs.append(TeamSpec(name, slug, email, seed))
    if not specs and not errors:
        errors.append({'row': 1, 'code': 'EMPTY', 'message': 'Tệp CSV không có dòng dữ liệu'})
    return specs, errors
