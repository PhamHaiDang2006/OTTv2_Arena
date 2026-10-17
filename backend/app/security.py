"""Passwords (argon2id), access JWT (15 min, HS256) and opaque refresh tokens (hash stored)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import get_settings
from app.timeutil import utcnow

ACCESS_TTL_SECONDS = 900  # Auth.expires_in is const 900 in the contract
REFRESH_TTL = timedelta(days=7)
REFRESH_COOKIE = 'ottv2_refresh'
REFRESH_COOKIE_PATH = '/api/v1/auth'
_hasher = PasswordHasher()
# Verifying against a fixed hash when the user is unknown keeps login timing uniform.
_DUMMY_HASH = _hasher.hash('ottv2-dummy-password')


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


class TokenError(Exception):
    def __init__(self, expired: bool):
        super().__init__('expired' if expired else 'invalid')
        self.expired = expired


def issue_access_token(user_id: uuid.UUID, role: str) -> str:
    now = utcnow()
    claims = {'sub': str(user_id), 'role': role, 'typ': 'access', 'iat': now,
              'exp': now + timedelta(seconds=ACCESS_TTL_SECONDS), 'jti': str(uuid.uuid4())}
    return jwt.encode(claims, get_settings().jwt_secret, algorithm='HS256')


def decode_access_token(token: str) -> dict:
    try:
        claims = jwt.decode(token, get_settings().jwt_secret, algorithms=['HS256'],
                            options={'require': ['sub', 'exp', 'iat', 'typ']})
    except jwt.ExpiredSignatureError as exc:
        raise TokenError(expired=True) from exc
    except jwt.PyJWTError as exc:
        raise TokenError(expired=False) from exc
    if claims.get('typ') != 'access':
        raise TokenError(expired=False)
    try:
        uuid.UUID(claims['sub'])
    except (ValueError, TypeError) as exc:
        raise TokenError(expired=False) from exc
    return claims


def new_refresh_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hash_refresh_token(token)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def worker_token_ok(presented: str) -> bool:
    return hmac.compare_digest(presented.encode('utf-8'), get_settings().worker_api_token.encode('utf-8'))
