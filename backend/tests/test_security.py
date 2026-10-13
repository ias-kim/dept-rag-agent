from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.security import (
    InvalidToken,
    decode_token,
    hash_password,
    issue_token,
    verify_password,
)

SECRET = "s" * 32
NOW = datetime(2026, 10, 1, tzinfo=UTC)


def test_password_round_trip():
    h = hash_password("correct horse")
    assert h != "correct horse"
    assert verify_password("correct horse", h) is True
    assert verify_password("wrong", h) is False


def test_unknown_user_is_false_and_garbage_hash_is_false():
    assert verify_password("anything", None) is False
    assert verify_password("anything", "not-an-argon2-hash") is False


def test_token_round_trip_carries_only_user_id():
    # 역할·과목을 토큰에 넣으면 수강 취소 뒤에도 만료까지 옛 권한이 남는다
    token = issue_token(7, secret=SECRET, ttl_hours=12)
    assert decode_token(token, secret=SECRET) == 7
    assert set(jwt.decode(token, SECRET, algorithms=["HS256"])) == {"sub", "iat", "exp"}


def test_decode_rejects_expired_token():
    token = issue_token(7, secret=SECRET, ttl_hours=1, now=NOW - timedelta(hours=2))
    with pytest.raises(InvalidToken):
        decode_token(token, secret=SECRET)


def test_decode_rejects_wrong_secret_and_garbage():
    token = issue_token(7, secret=SECRET, ttl_hours=1)
    with pytest.raises(InvalidToken):
        decode_token(token, secret="x" * 32)
    with pytest.raises(InvalidToken):
        decode_token("not.a.token", secret=SECRET)


def test_decode_rejects_missing_sub_and_none_alg():
    no_sub = jwt.encode({"exp": NOW + timedelta(days=999)}, SECRET, algorithm="HS256")
    none_alg = jwt.encode({"sub": "7", "exp": NOW + timedelta(days=999)}, None, algorithm="none")
    for bad in (no_sub, none_alg):
        with pytest.raises(InvalidToken):
            decode_token(bad, secret=SECRET)


def test_short_secret_is_refused():
    # 기본값 ""로 조용히 서명하면 누구나 같은 키로 토큰을 위조할 수 있다
    with pytest.raises(ValueError, match="JWT_SECRET"):
        issue_token(7, secret="", ttl_hours=1)
    with pytest.raises(ValueError, match="JWT_SECRET"):
        decode_token("x", secret="short")
