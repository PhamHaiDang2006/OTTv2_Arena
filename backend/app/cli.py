"""Operational commands: `uv run python -m app.cli <command>` (run from backend/)."""
from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys
import uuid

from sqlalchemy import func, select

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def migrate(revision: str = 'head') -> None:
    from alembic import command
    from alembic.config import Config
    command.upgrade(Config(os.path.join(BACKEND_DIR, 'alembic.ini')), revision)


def _password(args=None) -> str:
    value = os.environ.get('OTTV2_PASSWORD') or (getpass.getpass('Mật khẩu: ') if sys.stdin.isatty() else '')
    if len(value) < 8:
        raise SystemExit('Mật khẩu tối thiểu 8 ký tự (đặt OTTV2_PASSWORD hoặc nhập tương tác).')
    return value


def create_admin(email: str, password: str) -> uuid.UUID:
    from app.db import session_scope
    from app.models import TeamMember, User
    from app.security import hash_password
    with session_scope() as db:
        user = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
        if user is None:
            user = User(email=email.lower(), role='admin', is_active=True)
            db.add(user)
        elif db.scalar(select(TeamMember.team_id).where(TeamMember.user_id == user.id)) is not None:
            raise SystemExit('Tài khoản đang thuộc một đội, không thể làm admin.')
        user.role, user.password_hash = 'admin', hash_password(password)
        db.flush()
        return user.id


def set_password(email: str, password: str) -> None:
    from app.db import session_scope
    from app.models import User
    from app.security import hash_password
    with session_scope() as db:
        user = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
        if user is None:
            raise SystemExit('Không tìm thấy tài khoản.')
        user.password_hash = hash_password(password)


def add_member(team_slug: str, email: str, password: str | None) -> uuid.UUID:
    """Attach a member account to a team (the HTTP contract only creates captains)."""
    from app.db import session_scope
    from app.models import Team, TeamMember, User
    from app.security import hash_password
    with session_scope() as db:
        team = db.scalar(select(Team).where(Team.slug == team_slug))
        if team is None:
            raise SystemExit('Không tìm thấy đội.')
        user = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
        if user is None:
            user = User(email=email.lower(), role='member', is_active=True)
            db.add(user)
            db.flush()
        elif user.role == 'admin' or db.scalar(select(TeamMember.team_id).where(TeamMember.user_id == user.id)):
            raise SystemExit('Tài khoản là admin hoặc đã thuộc một đội.')
        if password:
            user.password_hash = hash_password(password)
        db.add(TeamMember(team_id=team.id, user_id=user.id))
        return user.id


def seed_dev(password: str) -> None:
    """Development data: one admin and two approved teams (captain accounts), no bots yet."""
    from app.admin.teams import TeamSpec, create_team
    from app.db import session_scope
    from app.models import Team, User
    from app.security import hash_password
    admin_id = create_admin('admin@example.test', password)
    with session_scope() as db:
        for index, slug in enumerate(('doi-a', 'doi-b'), start=1):
            if db.scalar(select(Team.id).where(Team.slug == slug)) is None:
                team = create_team(db, admin_id, TeamSpec(f'Đội {slug[-1].upper()}', slug,
                                                          f'captain-{slug}@example.test', index), 'team.seed_dev')
                team.status = 'approved'
        for user in db.scalars(select(User).where(User.email.like('captain-doi-%@example.test'))):
            user.password_hash = hash_password(password)
    print('admin@example.test, captain-doi-a@example.test, captain-doi-b@example.test (mật khẩu đã cung cấp)')


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    parser = argparse.ArgumentParser(prog='python -m app.cli')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('migrate', help='alembic upgrade head')
    for name in ('create-admin', 'set-password'):
        p = sub.add_parser(name)
        p.add_argument('--email', required=True)
    p = sub.add_parser('add-member', help='attach a member account to a team')
    p.add_argument('--team', required=True, help='team slug')
    p.add_argument('--email', required=True)
    p.add_argument('--no-password', action='store_true', help='create without password (set later)')
    sub.add_parser('seed-dev', help='admin + 2 approved teams (development only)')
    sub.add_parser('ensure-bucket', help='create S3 bucket if missing (development)')
    p = sub.add_parser('scheduler', help='outbox delivery, lease watchdog, scheduled freeze, similarity')
    p.add_argument('--stop-after', type=float, default=None, help=argparse.SUPPRESS)
    p = sub.add_parser('similarity', help='recompute similarity for a round snapshot')
    p.add_argument('--round-id', required=True)
    args = parser.parse_args(argv)
    if args.command == 'migrate':
        migrate()
    elif args.command == 'create-admin':
        print(create_admin(args.email, _password(args)))
    elif args.command == 'set-password':
        set_password(args.email, _password(args))
    elif args.command == 'add-member':
        print(add_member(args.team, args.email, None if args.no_password else _password(args)))
    elif args.command == 'seed-dev':
        seed_dev(_password(args))
    elif args.command == 'ensure-bucket':
        from app.storage import get_storage
        get_storage().ensure_bucket()
    elif args.command == 'scheduler':
        from app.scheduler import run
        run(args.stop_after)
    elif args.command == 'similarity':
        from app.db import session_scope
        from app.models import RoundSnapshot
        from app.similarity import compute_for_snapshot
        with session_scope() as db:
            snapshot_id = db.scalar(select(RoundSnapshot.id).where(RoundSnapshot.round_id == uuid.UUID(args.round_id)))
        if snapshot_id is None:
            raise SystemExit('Vòng chưa có snapshot.')
        print(compute_for_snapshot(snapshot_id))


if __name__ == '__main__':
    main()
