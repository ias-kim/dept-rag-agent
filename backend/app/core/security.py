"""비밀번호(argon2)와 토큰(JWT HS256) — 설계 §4.

토큰 payload는 user_id(sub)만 담는다. 역할·과목을 넣으면 수강이 바뀌어도 만료 전까지 옛 권한이 남으므로
요청마다 DB에서 다시 꺼낸다.
"""

from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_SECRET_CHARS = 32
ALGORITHM = "HS256"
_hasher = PasswordHasher()


class InvalidToken(Exception):
    """만료·위조·형식 오류 토큰."""


@lru_cache
def _dummy_hash() -> str:
    return _hasher.hash("dummy-password-for-constant-time")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """사용자가 없어도(None) 더미 해시로 한 번 검증한다. 건너뛰면 응답 시간 차이로 계정 존재 여부가 드러난다."""
    try:
        _hasher.verify(password_hash if password_hash is not None else _dummy_hash(), password)
    except (VerificationError, InvalidHashError):
        return False
    return password_hash is not None


def _require_secret(secret: str) -> None:
    if len(secret) < MIN_SECRET_CHARS:  # 빈 키로 서명하면 누구나 토큰을 위조할 수 있다
        raise ValueError(f"JWT_SECRET이 비었거나 {MIN_SECRET_CHARS}자 미만입니다")


def issue_token(user_id: int, *, secret: str, ttl_hours: int, now: datetime | None = None) -> str:
    _require_secret(secret)
    now = now or datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(hours=ttl_hours)}
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_token(token: str, *, secret: str) -> int:
    _require_secret(secret)
    try:
        # algorithms를 고정하지 않으면 alg="none" 토큰이 서명 없이 통과할 수 있다
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError) as e:
        raise InvalidToken(str(e)) from e
