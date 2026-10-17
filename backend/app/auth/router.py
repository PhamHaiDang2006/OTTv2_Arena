"""Login / refresh / logout / me per contracts/behavior.md (JWT 15 min, rotating opaque refresh cookie)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app import ratelimit
from app import serializers as ser
from app.config import get_settings
from app.db import get_db
from app.deps import Actor, OpInput, contract_input, load_actor, require_member
from app.errors import ApiError
from app.models import RefreshToken, RefreshTokenFamily, User
from app.security import (
    ACCESS_TTL_SECONDS,
    REFRESH_COOKIE,
    REFRESH_COOKIE_PATH,
    REFRESH_TTL,
    hash_refresh_token,
    issue_access_token,
    new_refresh_token,
    verify_password,
)
from app.timeutil import utcnow

router = APIRouter()


def check_origin(request: Request) -> None:
    """Browser session endpoints require an allow-listed Origin (CSRF defence for the cookie)."""
    origin = (request.headers.get('origin') or '').rstrip('/')
    if not origin or origin not in get_settings().origins:
        raise ApiError(403, 'FORBIDDEN', 'Origin không được phép', {'reason': 'origin'})


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(REFRESH_COOKIE, token, max_age=int(REFRESH_TTL.total_seconds()), path=REFRESH_COOKIE_PATH,
                        httponly=True, secure=get_settings().cookie_secure, samesite='strict')


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, httponly=True,
                           secure=get_settings().cookie_secure, samesite='strict')


def _auth_body(actor: Actor) -> dict:
    return {'access_token': issue_access_token(actor.id, actor.user.role), 'token_type': 'bearer',
            'expires_in': ACCESS_TTL_SECONDS, 'user': ser.user(actor.user, actor.team_id)}


def _issue_refresh(db: Session, family_id) -> str:
    token, digest = new_refresh_token()
    db.add(RefreshToken(family_id=family_id, token_hash=digest, expires_at=utcnow() + REFRESH_TTL))
    return token


@router.post('/auth/login')
def login(request: Request, _origin: None = Depends(check_origin), inp: OpInput = Depends(contract_input('login')),
          db: Session = Depends(get_db)):
    email = inp.body['email'].strip().lower()
    client = request.client.host if request.client else 'unknown'
    ratelimit.hit('login', f'{client}:{email}', get_settings().login_rate_per_minute, 60)
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if not verify_password(user.password_hash if user else None, inp.body['password']) or not user.is_active:
        raise ApiError(401, 'UNAUTHORIZED', 'Email hoặc mật khẩu không đúng')
    actor = load_actor(db, user.id)
    family = RefreshTokenFamily(user_id=user.id)
    db.add(family)
    db.flush()
    token = _issue_refresh(db, family.id)
    db.commit()
    response = JSONResponse(_auth_body(actor))
    _set_cookie(response, token)
    return response


@router.post('/auth/refresh')
def refresh(request: Request, _origin: None = Depends(check_origin), db: Session = Depends(get_db)):
    presented = request.cookies.get(REFRESH_COOKIE)
    if not presented:
        raise ApiError(401, 'UNAUTHORIZED', 'Thiếu refresh cookie')
    now = utcnow()
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(presented))
                    .with_for_update())
    family = db.get(RefreshTokenFamily, row.family_id, with_for_update=True) if row else None
    if row is None or family is None or family.revoked_at is not None:
        raise ApiError(401, 'UNAUTHORIZED')
    if row.used_at is not None:
        # Reuse of a rotated token: assume theft, revoke the whole family.
        family.revoked_at, family.revoked_reason = now, 'reuse_detected'
        db.commit()
        raise ApiError(401, 'UNAUTHORIZED', 'Refresh token đã được sử dụng')
    if row.expires_at <= now:
        raise ApiError(401, 'UNAUTHORIZED', 'Phiên đã hết hạn')
    actor = load_actor(db, family.user_id)
    if actor is None:
        raise ApiError(401, 'UNAUTHORIZED')
    row.used_at = now
    token = _issue_refresh(db, family.id)
    db.commit()
    response = JSONResponse(_auth_body(actor))
    _set_cookie(response, token)
    return response


@router.post('/auth/logout', status_code=204)
def logout(request: Request, _origin: None = Depends(check_origin), db: Session = Depends(get_db)):
    presented = request.cookies.get(REFRESH_COOKIE)
    if not presented:
        raise ApiError(401, 'UNAUTHORIZED', 'Thiếu refresh cookie')
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(presented)))
    if row is not None:
        db.execute(update(RefreshTokenFamily).where(RefreshTokenFamily.id == row.family_id,
                                                    RefreshTokenFamily.revoked_at.is_(None))
                   .values(revoked_at=utcnow(), revoked_reason='logout'))
        db.commit()
    response = Response(status_code=204)
    _clear_cookie(response)
    return response


@router.get('/auth/me')
def current_user(actor: Actor = Depends(require_member)):
    return ser.user(actor.user, actor.team_id)
