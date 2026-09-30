# M3 로그인·라우터·질문 API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사전 생성 계정으로 로그인해 JWT를 받고, `/api/ask`로 질문하면 일일 한도 안에서 의도 분류(LLM) → 처리 표(코드) → 권한 안의 MCP 도구 검색 → 출처 검증 답변을 돌려주는 4주차 워크플로우를 만들고, 평가에서 라우터 효과(의도 정확도)를 측정할 수 있게 한다.

**Architecture:** `app/db`에 계정·수강·사용량 저장소를 두고(원자 한도 증가), `app/core/security.py`가 argon2 비밀번호와 HS256 JWT를, `app/core/router.py`가 분류(`classify`)와 처리 표(`plan`)를 맡는다. `app/core/pipeline.py`는 `mode="baseline"|"workflow"`로 기준선과 라우터를 같은 코드에서 돌리고, 동기 Anthropic SDK 호출은 `anyio.to_thread`로 이벤트 루프 밖에서 부른다. `app/api`는 인증·한도·입력 검증·오류 변환만 하고 답변은 주입된 `answer_fn`에 맡긴다.

**Tech Stack:** Python 3.12, FastAPI 0.141.1, PyJWT 2.15.1, argon2-cffi 25.1.0, anthropic 1.8.0(동기 클라이언트, `messages.create`·`beta.messages.create`), anyio, M1·M2의 SQLAlchemy/pgvector/MCP 스택

**Spec:** [`docs/design/2026-09-28-system-design.md`](../../design/2026-09-28-system-design.md) — §2 흐름, §3 users·enrollments·usage_daily, §4 로그인·일일 한도, §5 라우터·처리 표, §6 평가, §8 M3

## Global Constraints

- Python 3.12, 모든 의존성 `==` 고정. 계층 `api → core → mcp → db` 역방향 import 금지(`app.core.config`만 예외).
- **역할·수강 과목은 토큰 → DB에서 서버가 꺼낸다.** JWT payload는 `sub`(user_id 문자열)·`iat`·`exp`뿐. 분류 프롬프트·도구 인자에 역할·과목을 넣지 않는다(분류기는 역할을 모른다).
- JWT: HS256, `jwt.decode(..., algorithms=["HS256"], options={"require": ["exp", "sub"]})`. `jwt_secret`이 비었거나 32자 미만이면 **발급·검증 모두 거부**(`ValueError`).
- 로그인 실패는 사용자 없음/비밀번호 틀림 모두 같은 401·같은 문구. 사용자 없음도 더미 해시로 argon2 검증을 한 번 수행한다.
- 비밀번호는 `getpass` 또는 `--password-stdin`으로만 받는다. argv·로그·출력에 남기지 않는다.
- "오늘"은 `Asia/Seoul` 기준(`app/core/clock.py`의 `seoul_today`). 서버(EC2)는 UTC다.
- 한도 순서: **입력 검증(422) → 한도 소비(429) → 답변**. 상류(LLM·임베딩) 오류(503)일 때만 한도를 되돌린다.
- 분류 모델은 설정값 `classify_model = "claude-haiku-4-5-20251001"`, `client.messages.create(model, max_tokens, system, messages)`만 쓴다 — `effort`·fallback beta·`temperature`/`top_p`/`top_k`를 보내지 않는다. `stop_reason == "refusal"`이면 `content`를 읽지 않는다.
- 분류 출력이 네 라벨 중 하나가 아니면 `both`로 처리하되 `intent_valid=False`를 남겨 **평가에서는 오답**으로 센다(설계 §5).
- 테스트는 실제 Anthropic/OpenAI API를 호출하지 않는다(`FakeLLM`, `app.dependency_overrides`). 에이전트는 `.env`를 열거나 출력하지 않는다.
- 라우트를 바꾼 태스크는 같은 태스크에서 `make generate`로 `docs/generated/openapi.json`을 갱신해 커밋한다.
- 로컬 테스트 DB 포트 5433. 커밋: 한국어 conventional + `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. 각 태스크 끝에 `make check` 통과.
- **게이트 3 필수** — `backend/requirements.txt`, `backend/app/db/`, `backend/app/mcp/`, `.env.example`, `docs/harness/risk-paths.txt`가 바뀐다.

## Review Focus

1. **만료·위조·`sub` 없는 토큰, 삭제된 사용자의 토큰** — 전부 401 → Task 2 `test_decode_rejects_*`, Task 5 `test_ask_rejects_token_of_deleted_user`.
2. **비밀 키가 빈 설정으로 토큰 발급** — 기본값 `""`가 조용히 서명하면 누구나 토큰 위조 가능 → Task 2 `test_short_secret_is_refused`.
3. **한도 0인 계정의 첫 질문, 한도 도달 후 질문** — `INSERT … ON CONFLICT … WHERE`는 첫 INSERT에서 WHERE를 건너뛰므로 0 한도를 따로 막아야 한다 → Task 1 `test_zero_quota_never_consumes`, `test_consume_stops_at_limit`.
4. **분류기가 라벨이 아닌 말을 하거나 거절** — `both`로 동작하되 평가는 오답 → Task 3 `test_classify_garbage_falls_back_to_both_invalid`, Task 6 `test_intent_ok_requires_valid_label`.
5. **`none` 의도의 "범위 밖" 응답이 평가 none 처리 지표에서 실패로 잡힘** — `none_handled`가 `out_of_scope` 공지를 인정해야 한다 → Task 6 `test_none_handled_accepts_out_of_scope`.
6. **도구 하나가 실패** — 나머지 도구 결과로 답하고 공지를 남긴다 → Task 4 `test_one_failing_tool_does_not_sink_answer`.
7. **LLM 장애** — 한도 되돌림 + 503, 400번대 오류는 되돌리지 않음 → Task 5 `test_upstream_error_refunds_quota`, `test_invalid_question_does_not_consume_quota`.

## 완료 기준

- [ ] 계정·수강·사용량 저장소, 원자 한도 소비·되돌림 — DB 테스트 통과
- [ ] argon2 비밀번호, HS256 JWT(필수 클레임·짧은 키 거부), `make users` CLI
- [ ] `classify`(Haiku, 형식 오류 → both·invalid)·`plan`(처리 표) — 실제 API 없이 테스트 통과
- [ ] 파이프라인 `mode=baseline|workflow`, 도구 실패 격리, 오늘 날짜 주입, 동기 SDK의 스레드 호출
- [ ] `POST /api/auth/login`, `POST /api/ask`(401·422·429·503), OpenAPI 스냅샷 갱신
- [ ] 평가 `MODE=`·의도 정확도 지표·비교표 열 추가, 이전 실행은 `—`
- [ ] 문서: SoT·AGENTS·`.env.example`·위험 경로·설계 정정, M2 계획 done 이동
- [ ] (튜터) `JWT_SECRET` 설정, 계정 생성, 같은 코드에서 `baseline-v2`·`router-v1` 측정 → 채점 → 비교표

## 파일 구조

| 파일 | 책임 |
|---|---|
| `backend/app/db/accounts.py` | `find_user`, `get_user`, `user_courses`, `upsert_user` |
| `backend/app/db/usage.py` | `consume_quota`(원자), `refund_quota`, `used_on` |
| `backend/app/core/clock.py` | `SEOUL`, `seoul_today` |
| `backend/app/core/security.py` | `hash_password`, `verify_password`, `issue_token`, `decode_token`, `InvalidToken` |
| `backend/app/core/users.py` | `add_user`, CLI `python -m app.core.users add …` (`make users`) |
| `backend/app/core/prompts/classify.md` | 의도 분류 시스템 프롬프트 (**프롬프트 SoT**) |
| `backend/app/core/router.py` | `INTENTS`, `Classification`, `parse_intent`, `classify`, `Plan`, `plan`, `classify_prompt_hash` |
| `backend/app/core/pipeline.py` | `MODES`, `UpstreamError`, `answer_question(…, mode)` |
| `backend/app/core/answer.py` | `Answer.intent`·`intent_valid`, `render_context(…, today)` |
| `backend/app/api/deps.py` | `get_session`, `AuthedUser`, `current_user`, `get_answer_fn` |
| `backend/app/api/routes.py` | `/api/auth/login`, `/api/ask`, 요청·응답 모델 |
| `backend/evaluation/{metrics,run,report}.py` | `intent_ok`, `--mode`, 모드·의도 정확도 열 |

---

### Task 1: 설정·의존성, 계정·사용량 저장소 (db)

**Files:**
- Modify: `backend/requirements.txt`, `backend/app/core/config.py`, `.env.example`, `backend/tests/test_dependency_floor.py`
- Create: `backend/app/db/accounts.py`, `backend/app/db/usage.py`
- Test: `backend/tests/db/test_accounts.py`, `backend/tests/db/test_usage.py`

**Interfaces:**
- Produces: `find_user(session, username) -> User | None`, `get_user(session, user_id) -> User | None`, `user_courses(session, user_id) -> frozenset[str]`, `upsert_user(session, *, username, password_hash, courses: frozenset[str], daily_quota: int) -> User` (flush만, commit 안 함)
- Produces: `consume_quota(session, user_id, day, *, limit) -> bool`, `refund_quota(session, user_id, day) -> None`, `used_on(session, user_id, day) -> int` (모두 commit 안 함)
- Produces (설정): `jwt_secret: str = ""`, `jwt_ttl_hours: int = 12`, `classify_model: str = "claude-haiku-4-5-20251001"`, `classify_max_tokens: int = 16`, `router_mode: str = "workflow"`, `default_daily_quota: int = 50`

- [ ] **Step 1: 의존성·설정 추가**

`backend/requirements.txt`에 두 줄(알파벳 순서 위치):

```
argon2-cffi==25.1.0
PyJWT==2.15.1
```

`backend/app/core/config.py`의 `Settings`에 `search_min_score` 아래로:

```python
    jwt_secret: str = ""  # 32자 이상. 비면 토큰 발급·검증 거부 (app/core/security.py)
    jwt_ttl_hours: int = 12
    classify_model: str = "claude-haiku-4-5-20251001"
    classify_max_tokens: int = 16
    router_mode: str = "workflow"  # "baseline" | "workflow" — app/core/pipeline.py MODES
    default_daily_quota: int = 50
```

`.env.example` 끝에 `JWT_SECRET=` 한 줄. `tests/test_dependency_floor.py`의 import 목록에 `"jwt"`, `"argon2"` 추가. `make setup`으로 설치.

- [ ] **Step 2: 실패하는 테스트 작성** — `backend/tests/db/test_accounts.py`

```python
from app.db.accounts import find_user, get_user, upsert_user, user_courses


def test_upsert_creates_user_with_courses(session):
    user = upsert_user(session, username="kim", password_hash="h", courses=frozenset({"AGENT", "AWS"}), daily_quota=30)
    assert find_user(session, "kim").id == user.id
    assert user_courses(session, user.id) == frozenset({"AGENT", "AWS"})
    assert get_user(session, user.id).daily_quota == 30


def test_upsert_replaces_courses_and_password(session):
    user = upsert_user(session, username="kim", password_hash="old", courses=frozenset({"AGENT"}), daily_quota=50)
    again = upsert_user(session, username="kim", password_hash="new", courses=frozenset({"DB"}), daily_quota=10)
    assert again.id == user.id and again.password_hash == "new"
    assert user_courses(session, user.id) == frozenset({"DB"})


def test_guest_has_no_courses(session):
    user = upsert_user(session, username="guest", password_hash="h", courses=frozenset(), daily_quota=5)
    assert user_courses(session, user.id) == frozenset()


def test_unknown_user_is_none(session):
    assert find_user(session, "nobody") is None and get_user(session, 999) is None
```

`backend/tests/db/test_usage.py`

```python
from datetime import date

from app.db.accounts import upsert_user
from app.db.usage import consume_quota, refund_quota, used_on

DAY = date(2026, 10, 1)


def make_user(session, quota=2):
    return upsert_user(session, username="kim", password_hash="h", courses=frozenset(), daily_quota=quota).id


def test_consume_stops_at_limit(session):
    uid = make_user(session)
    assert [consume_quota(session, uid, DAY, limit=2) for _ in range(3)] == [True, True, False]
    assert used_on(session, uid, DAY) == 2  # 거절된 호출은 세지 않는다


def test_zero_quota_never_consumes(session):
    uid = make_user(session, quota=0)
    assert consume_quota(session, uid, DAY, limit=0) is False
    assert used_on(session, uid, DAY) == 0


def test_days_are_counted_separately(session):
    uid = make_user(session, quota=1)
    assert consume_quota(session, uid, DAY, limit=1) is True
    assert consume_quota(session, uid, date(2026, 10, 2), limit=1) is True


def test_refund_gives_back_one_and_never_goes_negative(session):
    uid = make_user(session)
    consume_quota(session, uid, DAY, limit=2)
    refund_quota(session, uid, DAY)
    refund_quota(session, uid, DAY)
    assert used_on(session, uid, DAY) == 0
```

- [ ] **Step 3: RED 확인** — `make test` → `ModuleNotFoundError: app.db.accounts`

- [ ] **Step 4: 구현** — `backend/app/db/accounts.py`

```python
"""계정·수강 저장소 — 설계 §3·§4. 역할 컬럼 없음: 전공 접근은 enrollments 행 존재로만 판단한다."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Enrollment, User


def find_user(session: Session, username: str) -> User | None:
    return session.scalars(select(User).where(User.username == username)).one_or_none()


def get_user(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def user_courses(session: Session, user_id: int) -> frozenset[str]:
    return frozenset(session.scalars(select(Enrollment.course_code).where(Enrollment.user_id == user_id)))


def upsert_user(session: Session, *, username: str, password_hash: str, courses: frozenset[str],
                daily_quota: int) -> User:
    user = find_user(session, username)
    if user is None:
        user = User(username=username, password_hash=password_hash, daily_quota=daily_quota)
        session.add(user)
        session.flush()
    else:
        user.password_hash = password_hash
        user.daily_quota = daily_quota
    session.execute(delete(Enrollment).where(Enrollment.user_id == user.id))
    session.add_all(Enrollment(user_id=user.id, course_code=c) for c in sorted(courses))
    session.flush()
    return user
```

`backend/app/db/usage.py`

```python
"""일일 질문 한도 — 설계 §4. 한 문장으로 원자 증가하고, 한도에 닿으면 행을 바꾸지 않는다."""

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

_CONSUME = text("""
INSERT INTO usage_daily (user_id, day, count) VALUES (:uid, :day, 1)
ON CONFLICT (user_id, day) DO UPDATE SET count = usage_daily.count + 1
WHERE usage_daily.count < :limit
RETURNING count
""")
_REFUND = text("UPDATE usage_daily SET count = GREATEST(count - 1, 0) WHERE user_id = :uid AND day = :day")
_USED = text("SELECT count FROM usage_daily WHERE user_id = :uid AND day = :day")


def consume_quota(session: Session, user_id: int, day: date, *, limit: int) -> bool:
    if limit <= 0:  # 첫 INSERT는 WHERE를 거치지 않으므로 0 한도는 여기서 막는다
        return False
    return session.execute(_CONSUME, {"uid": user_id, "day": day, "limit": limit}).scalar_one_or_none() is not None


def refund_quota(session: Session, user_id: int, day: date) -> None:
    session.execute(_REFUND, {"uid": user_id, "day": day})


def used_on(session: Session, user_id: int, day: date) -> int:
    return session.execute(_USED, {"uid": user_id, "day": day}).scalar_one_or_none() or 0
```

- [ ] **Step 5: GREEN 확인** — `make check`
- [ ] **Step 6: 커밋** — `feat(db): 계정·수강·일일 한도 저장소와 M3 설정`

---

### Task 2: 비밀번호·토큰과 계정 CLI (core)

**Files:**
- Create: `backend/app/core/clock.py`, `backend/app/core/security.py`, `backend/app/core/users.py`
- Modify: `Makefile` (`users` 타깃, `.PHONY`)
- Test: `backend/tests/test_security.py`, `backend/tests/test_clock.py`, `backend/tests/db/test_users_cli.py`

**Interfaces:**
- Consumes: Task 1 `upsert_user`, `Settings.jwt_secret`·`jwt_ttl_hours`·`default_daily_quota`
- Produces: `seoul_today(now: datetime | None = None) -> date`, `hash_password(str) -> str`, `verify_password(password: str, password_hash: str | None) -> bool`, `issue_token(user_id: int, *, secret: str, ttl_hours: int, now: datetime | None = None) -> str`, `decode_token(token: str, *, secret: str) -> int`, `InvalidToken`, `add_user(session, username, password, *, courses: str, quota: int) -> User`

- [ ] **Step 1: 실패하는 테스트 작성** — `backend/tests/test_clock.py`

```python
from datetime import UTC, date, datetime

from app.core.clock import seoul_today


def test_seoul_date_rolls_over_at_15_utc():
    assert seoul_today(datetime(2026, 9, 30, 14, 59, tzinfo=UTC)) == date(2026, 9, 30)
    assert seoul_today(datetime(2026, 9, 30, 15, 0, tzinfo=UTC)) == date(2026, 10, 1)
```

`backend/tests/test_security.py`

```python
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.security import InvalidToken, decode_token, hash_password, issue_token, verify_password

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
    with pytest.raises(ValueError, match="JWT_SECRET"):
        issue_token(7, secret="", ttl_hours=1)
    with pytest.raises(ValueError, match="JWT_SECRET"):
        decode_token("x", secret="short")
```

`backend/tests/db/test_users_cli.py`

```python
import pytest

from app.core.security import verify_password
from app.core.users import add_user, build_parser
from app.db.accounts import user_courses


def test_add_user_normalizes_courses_and_hashes_password(session):
    user = add_user(session, "kim", "password123", courses="agent, aws ,", quota=20)
    assert user_courses(session, user.id) == frozenset({"AGENT", "AWS"})
    assert verify_password("password123", user.password_hash)


def test_short_password_is_rejected(session):
    with pytest.raises(ValueError, match="8자"):
        add_user(session, "kim", "short", courses="", quota=5)


def test_password_cannot_be_passed_as_argument():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["add", "kim", "--password", "secret123"])
```

- [ ] **Step 2: RED 확인** — `make test`

- [ ] **Step 3: 구현** — `backend/app/core/clock.py`

```python
"""서비스 기준 시각 — 서버는 UTC, 한도·날짜 안내는 한국 날짜 기준."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

SEOUL = ZoneInfo("Asia/Seoul")


def seoul_today(now: datetime | None = None) -> date:
    return (now or datetime.now(SEOUL)).astimezone(SEOUL).date()
```

`backend/app/core/security.py`

```python
"""비밀번호(argon2)와 토큰(JWT HS256) — 설계 §4. payload는 user_id(sub)만, 역할·과목은 DB에서 꺼낸다."""

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
    """사용자가 없어도(None) 더미 해시로 한 번 검증해 응답 시간으로 계정 존재를 드러내지 않는다."""
    try:
        _hasher.verify(password_hash if password_hash is not None else _dummy_hash(), password)
    except (VerificationError, InvalidHashError):
        return False
    return password_hash is not None


def _require_secret(secret: str) -> None:
    if len(secret) < MIN_SECRET_CHARS:
        raise ValueError(f"JWT_SECRET이 비었거나 {MIN_SECRET_CHARS}자 미만입니다")


def issue_token(user_id: int, *, secret: str, ttl_hours: int, now: datetime | None = None) -> str:
    _require_secret(secret)
    now = now or datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(hours=ttl_hours)}
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_token(token: str, *, secret: str) -> int:
    _require_secret(secret)
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError) as e:
        raise InvalidToken(str(e)) from e
```

`backend/app/core/users.py`

```python
"""계정 CLI — `make users ARGS="add kim --courses AGENT,AWS"`. 회원가입 API는 없다(설계 §4).

비밀번호는 getpass 또는 --password-stdin으로만 받는다. argv·출력에 남기지 않는다.
"""

import argparse
import getpass
import sys

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.accounts import upsert_user
from app.db.models import User
from app.db.session import make_engine

MIN_PASSWORD_CHARS = 8


def add_user(session: Session, username: str, password: str, *, courses: str, quota: int) -> User:
    if len(password) < MIN_PASSWORD_CHARS:
        raise ValueError(f"비밀번호는 {MIN_PASSWORD_CHARS}자 이상이어야 합니다")
    codes = frozenset(c.strip().upper() for c in courses.split(",") if c.strip())
    return upsert_user(session, username=username, password_hash=hash_password(password),
                       courses=codes, daily_quota=quota)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.core.users")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add", help="계정 생성 또는 갱신(비밀번호·과목·한도 덮어씀)")
    add.add_argument("username")
    add.add_argument("--courses", default="", help="쉼표로 구분한 과목 코드. 비우면 게스트(학사만)")
    add.add_argument("--quota", type=int, default=None, help="일일 질문 한도 (기본: 설정값)")
    add.add_argument("--password-stdin", action="store_true", help="표준입력 첫 줄을 비밀번호로 사용")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    password = sys.stdin.readline().rstrip("\n") if args.password_stdin else getpass.getpass("비밀번호: ")
    quota = args.quota if args.quota is not None else get_settings().default_daily_quota
    with Session(make_engine()) as session:
        user = add_user(session, args.username, password, courses=args.courses, quota=quota)
        courses = sorted(c for c in args.courses.upper().replace(" ", "").split(",") if c)
        session.commit()
    print(f"계정 저장: {user.username} (과목 {courses or '없음'}, 일일 한도 {quota})")


if __name__ == "__main__":
    main()
```

`Makefile` — `.PHONY`에 `users` 추가, `ingest` 타깃 아래:

```make
users:
	PYTHONPATH=backend $(PY) -m app.core.users $(ARGS)
```

- [ ] **Step 4: GREEN 확인** — `make check`
- [ ] **Step 5: 커밋** — `feat(core): argon2 비밀번호·HS256 토큰·계정 CLI, 서울 기준 날짜`

---

### Task 3: 의도 분류와 처리 표 (core/router)

**Files:**
- Create: `backend/app/core/prompts/classify.md`, `backend/app/core/router.py`
- Modify: `backend/tests/fakes.py` (`FakeLLM`에 `messages.create` 추가)
- Test: `backend/tests/test_router.py`

**Interfaces:**
- Consumes: `app.mcp.server.UserContext`, `TOOL_ACADEMIC`, `TOOL_MAJOR`
- Produces: `INTENTS = ("major", "academic", "both", "none")`, `Classification(intent: str, valid: bool, raw: str)`, `parse_intent(text) -> str | None`, `classify(llm, question, *, model, max_tokens) -> Classification` (동기), `Plan(tools: tuple[str, ...], notices: tuple[str, ...])`, `plan(intent, user) -> Plan`, `classify_prompt_hash() -> str`
- 공지 코드: `major_requires_enrollment`, `out_of_scope`

- [ ] **Step 1: `FakeLLM` 확장** — `backend/tests/fakes.py`의 `FakeLLM`을 다음으로 바꾼다(기존 `beta.messages.create` 동작 유지)

```python
class FakeLLM:
    """anthropic 클라이언트 대역. 생성(beta.messages.create)과 분류(messages.create) 호출을 따로 기록한다."""

    def __init__(self, text: str = "", stop_reason: str = "end_turn", *, classify_text: str = "academic",
                 classify_stop: str = "end_turn"):
        self.calls: list[dict] = []
        self.classify_calls: list[dict] = []
        self.text = text
        self.stop_reason = stop_reason
        self.classify_text = classify_text
        self.classify_stop = classify_stop
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self.messages = SimpleNamespace(create=self._classify)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        content = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=self.text)]
        return SimpleNamespace(stop_reason=self.stop_reason, content=content if self.stop_reason != "refusal" else [])

    def _classify(self, **kwargs):
        self.classify_calls.append(kwargs)
        content = [SimpleNamespace(type="text", text=self.classify_text)] if self.classify_stop != "refusal" else []
        return SimpleNamespace(stop_reason=self.classify_stop, content=content)
```

- [ ] **Step 2: 실패하는 테스트 작성** — `backend/tests/test_router.py`

```python
import pytest

from app.core.router import Classification, Plan, classify, parse_intent, plan
from app.mcp.server import TOOL_ACADEMIC, TOOL_MAJOR, UserContext
from tests.fakes import FakeLLM

STUDENT = UserContext(user_id=1, courses=frozenset({"AGENT"}))
GUEST = UserContext(user_id=2, courses=frozenset())


@pytest.mark.parametrize("raw, expected", [
    ("academic", "academic"), (" Major.\n", "major"), ("BOTH", "both"), ("none", "none"),
    ("학사", None), ("academic because ...", None), ("", None),
])
def test_parse_intent(raw, expected):
    assert parse_intent(raw) == expected


def test_classify_sends_only_question_without_role_or_sampling():
    llm = FakeLLM(classify_text="major")
    result = classify(llm, "MCP Host가 뭐야?", model="claude-haiku-4-5-20251001", max_tokens=16)
    assert result == Classification("major", True, "major")
    call = llm.classify_calls[0]
    assert call["model"] == "claude-haiku-4-5-20251001" and call["max_tokens"] == 16
    assert call["messages"] == [{"role": "user", "content": "MCP Host가 뭐야?"}]
    assert not {"temperature", "top_p", "top_k", "output_config"} & set(call)
    assert "AGENT" not in call["system"]


def test_classify_garbage_falls_back_to_both_invalid():
    result = classify(FakeLLM(classify_text="잘 모르겠어요"), "q", model="m", max_tokens=16)
    assert (result.intent, result.valid) == ("both", False)


def test_classify_refusal_falls_back_to_both_invalid():
    result = classify(FakeLLM(classify_stop="refusal"), "q", model="m", max_tokens=16)
    assert result == Classification("both", False, "")


@pytest.mark.parametrize("intent, user, expected", [
    ("academic", STUDENT, Plan((TOOL_ACADEMIC,), ())),
    ("academic", GUEST, Plan((TOOL_ACADEMIC,), ())),
    ("major", STUDENT, Plan((TOOL_MAJOR,), ())),
    ("major", GUEST, Plan((), ("major_requires_enrollment",))),
    ("both", STUDENT, Plan((TOOL_ACADEMIC, TOOL_MAJOR), ())),
    ("both", GUEST, Plan((TOOL_ACADEMIC,), ("major_requires_enrollment",))),
    ("none", STUDENT, Plan((), ("out_of_scope",))),
    ("none", GUEST, Plan((), ("out_of_scope",))),
])
def test_plan_table(intent, user, expected):
    assert plan(intent, user) == expected


def test_plan_rejects_unknown_intent():
    with pytest.raises(ValueError):
        plan("other", STUDENT)
```

- [ ] **Step 3: RED 확인** — `make test`

- [ ] **Step 4: 구현** — `backend/app/core/prompts/classify.md`

```markdown
너는 학과 질의응답 서비스의 질문 분류기다. 학생 질문을 아래 네 라벨 중 하나로만 분류한다.

- academic: 학사·행정·공지 — 시간표, 강의실, 수강신청, 등록금, 장학, 학사일정, 학과 공지·행사, 교육 이수
- major: 전공 강의 내용 — 프로그래밍, 데이터베이스, 클라우드, AI·ML, 웹, 에이전트·MCP 등 개념·예제·코드
- both: 한 질문에 학사 정보와 전공 내용이 함께 필요함 (예: "그 수업은 몇 교시고 무엇을 배워?")
- none: 학과 자료와 무관함 — 학식, 날씨, 잡담, 학과에서 다루지 않는 기술

출력: 라벨 단어 하나만 소문자로 쓴다. 설명·문장부호·다른 말을 붙이지 않는다.
```

`backend/app/core/router.py`

```python
"""4주차 워크플로우 라우터 — 설계 §5. 분류(LLM, 역할 모름) → 처리 표(코드, 역할 앎)."""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.mcp.server import TOOL_ACADEMIC, TOOL_MAJOR, UserContext

INTENTS = ("major", "academic", "both", "none")
PROMPT_PATH = Path(__file__).parent / "prompts" / "classify.md"
NEEDS_ENROLLMENT = "major_requires_enrollment"
OUT_OF_SCOPE = "out_of_scope"


@dataclass(frozen=True)
class Classification:
    intent: str
    valid: bool  # False면 형식 오류·거절로 both 대체 — 평가에서는 오답
    raw: str


@dataclass(frozen=True)
class Plan:
    tools: tuple[str, ...]
    notices: tuple[str, ...]


def classify_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def classify_prompt_hash() -> str:
    return hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()[:12]


def parse_intent(text: str) -> str | None:
    word = text.strip().rstrip(".").strip().lower()
    return word if word in INTENTS else None


def classify(llm: Any, question: str, *, model: str, max_tokens: int) -> Classification:
    response = llm.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=classify_prompt(),
        messages=[{"role": "user", "content": question}],
    )
    if response.stop_reason == "refusal":
        return Classification("both", False, "")
    raw = "".join(block.text for block in response.content if block.type == "text").strip()
    intent = parse_intent(raw)
    return Classification(intent or "both", intent is not None, raw)


def plan(intent: str, user: UserContext) -> Plan:
    enrolled = bool(user.courses)
    if intent == "academic":
        return Plan((TOOL_ACADEMIC,), ())
    if intent == "major":
        return Plan((TOOL_MAJOR,), ()) if enrolled else Plan((), (NEEDS_ENROLLMENT,))
    if intent == "both":
        return Plan((TOOL_ACADEMIC, TOOL_MAJOR), ()) if enrolled else Plan((TOOL_ACADEMIC,), (NEEDS_ENROLLMENT,))
    if intent == "none":
        return Plan((), (OUT_OF_SCOPE,))
    raise ValueError(f"알 수 없는 의도: {intent!r}")
```

- [ ] **Step 5: GREEN 확인** — `make check`
- [ ] **Step 6: 커밋** — `feat(core): 의도 분류(Haiku)와 처리 표`

---

### Task 4: 파이프라인 workflow 모드와 M2 이월 항목

**Files:**
- Modify: `backend/app/core/answer.py`, `backend/app/core/prompts/answer.md`, `backend/app/core/pipeline.py`, `backend/app/mcp/server.py`
- Test: `backend/tests/test_answer.py`, `backend/tests/db/test_pipeline.py`, `backend/tests/db/test_mcp_server.py`

**Interfaces:**
- Consumes: Task 3 `classify`, `plan`, `OUT_OF_SCOPE`, `NEEDS_ENROLLMENT`; Task 2 `seoul_today`
- Produces: `Answer.intent: str | None = None`, `Answer.intent_valid: bool | None = None`; `render_context(question, hits, today: date | None = None)`; `generate_answer(..., today: date | None = None)`; `PipelineDeps.today: Callable[[], date] = seoul_today`; `MODES = ("baseline", "workflow")`; `UpstreamError`; `OUT_OF_SCOPE_TEXT`, `MAJOR_ONLY_TEXT`; `async answer_question(question, user, deps, *, mode="baseline") -> Answer`

- [ ] **Step 1: 실패하는 테스트 추가** — `backend/tests/test_answer.py` 끝에

```python
from datetime import date


def test_today_is_given_to_the_model_when_provided():
    llm = FakeLLM("답[C12].")
    generate_answer(llm, "q", [make_hit(12)], today=date(2026, 9, 30), **OPTS)
    assert llm.calls[0]["messages"][0]["content"].startswith("오늘 날짜: 2026-09-30\n")


def test_no_today_keeps_context_unchanged():
    llm = FakeLLM("답[C12].")
    generate_answer(llm, "q", [make_hit(12)], **OPTS)
    assert llm.calls[0]["messages"][0]["content"].startswith("<자료>")
```

`backend/tests/db/test_mcp_server.py`의 `test_empty_query_is_rejected` 아래에:

```python
async def test_non_string_query_is_rejected(session):
    # 목록·숫자를 str()로 바꿔 검색하지 않고 오류로 돌려준다
    for bad in (["a"], 123, None):
        with pytest.raises(ToolError, match="문자열"):
            await call(server_for(session, []), TOOL_ACADEMIC, {"query": bad})
```

`backend/tests/db/test_pipeline.py` 끝에 (`deps()`에 `today=lambda: date(2026, 9, 30)`을 넘기도록 헬퍼 수정 포함):

```python
from dataclasses import replace
from datetime import date

from app.core.pipeline import MAJOR_ONLY_TEXT, OUT_OF_SCOPE_TEXT
from app.mcp.connection import ToolError


@pytest.mark.anyio
async def test_workflow_academic_intent_searches_only_academic(session):
    seed_chunks(session, CORPUS)
    llm = FakeLLM("답[C1].", classify_text="academic")
    answer = await answer_question("수강신청 언제?", user("CS101"), deps(session, llm), mode="workflow")
    assert [h.source for h in answer.retrieved] == ["academic/calendar.pdf"]
    assert (answer.intent, answer.intent_valid) == ("academic", True)


@pytest.mark.anyio
async def test_workflow_none_intent_answers_without_search_or_generation(session):
    seed_chunks(session, CORPUS)
    llm = FakeLLM("무시됨", classify_text="none")
    answer = await answer_question("학식 뭐야?", user("CS101"), deps(session, llm), mode="workflow")
    assert answer.text == OUT_OF_SCOPE_TEXT and answer.sources == [] and llm.calls == []
    assert answer.notices == ["out_of_scope"] and answer.intent == "none"


@pytest.mark.anyio
async def test_workflow_major_intent_for_guest_explains_restriction(session):
    seed_chunks(session, CORPUS)
    llm = FakeLLM("무시됨", classify_text="major")
    answer = await answer_question("스택?", user(), deps(session, llm), mode="workflow")
    assert answer.text == MAJOR_ONLY_TEXT and llm.calls == []
    assert answer.notices == ["major_requires_enrollment"]


@pytest.mark.anyio
async def test_workflow_invalid_label_uses_both_and_is_marked(session):
    seed_chunks(session, CORPUS)
    llm = FakeLLM("답[C1].", classify_text="모르겠음")
    answer = await answer_question("q", user("CS101"), deps(session, llm), mode="workflow")
    assert (answer.intent, answer.intent_valid) == ("both", False)
    assert sorted(h.source for h in answer.retrieved) == ["academic/calendar.pdf", "major/CS101/lec1.pdf"]


@pytest.mark.anyio
async def test_baseline_mode_does_not_classify(session):
    seed_chunks(session, CORPUS)
    llm = FakeLLM("답[C1].")
    answer = await answer_question("q", user("CS101"), deps(session, llm))
    assert llm.classify_calls == [] and answer.intent is None


@pytest.mark.anyio
async def test_one_failing_tool_does_not_sink_answer(session, monkeypatch):
    seed_chunks(session, CORPUS)
    import app.core.pipeline as pipeline

    real = pipeline.parse_hits

    def flaky(result):
        hits = real(result)
        if hits and hits[0].scope == "major":
            raise ToolError("db down")
        return hits

    monkeypatch.setattr(pipeline, "parse_hits", flaky)
    answer = await answer_question("q", user("CS101"), deps(session, FakeLLM("답[C1].")))
    assert [h.source for h in answer.retrieved] == ["academic/calendar.pdf"]
    assert "tool_error:search_major" in answer.notices


@pytest.mark.anyio
async def test_blank_question_and_unknown_mode_are_rejected(session):
    with pytest.raises(ValueError):
        await answer_question("   ", user(), deps(session, FakeLLM()))
    with pytest.raises(ValueError):
        await answer_question("q", user(), deps(session, FakeLLM()), mode="agent")
```

- [ ] **Step 2: RED 확인** — `make test`

- [ ] **Step 3: 구현**

`backend/app/core/answer.py`:
- `Answer`에 필드 추가(맨 끝): `intent: str | None = None`, `intent_valid: bool | None = None`
- `render_context(question, hits, today: date | None = None)`: 반환 문자열 앞에 `today`가 있으면 `f"오늘 날짜: {today.isoformat()}\n\n"`을 붙인다.
- `generate_answer(..., max_tokens: int, today: date | None = None)`: `render_context(question, hits, today)`로 전달.

`backend/app/core/prompts/answer.md` 규칙 끝에 한 줄:

```markdown
7. 맨 앞에 `오늘 날짜`가 주어지면, 날짜가 이미 지난 일정·마감은 지났다고 함께 알려 준다.
```

`backend/app/mcp/server.py`의 `call_tool`에서 query 처리를 바꾼다:

```python
        raw_query = args.get("query", "")
        if not isinstance(raw_query, str):
            return _error("query는 문자열이어야 합니다")
        query = raw_query.strip()
```

`backend/app/core/pipeline.py`를 다음으로 바꾼다:

```python
"""질문 → 답변 워크플로우 (설계 §2·§5).

- baseline: 라우터 없이 권한 안에서 보이는 모든 검색 도구를 호출 (3주차 기준선)
- workflow: 분류(LLM) → 처리 표(코드) → 표가 고른 도구만 호출 (4주차)
동기 Anthropic SDK 호출은 anyio.to_thread로 이벤트 루프 밖에서 부른다.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

import anyio
from sqlalchemy.orm import Session

from app.core.answer import Answer, generate_answer
from app.core.clock import seoul_today
from app.core.config import Settings
from app.core.router import NEEDS_ENROLLMENT, classify, plan
from app.db.search import ChunkHit
from app.mcp.connection import ToolError, connect, parse_hits
from app.mcp.server import UserContext, build_server

MODES = ("baseline", "workflow")
OUT_OF_SCOPE_TEXT = "학과 전공자료·학사 공지 범위 밖의 질문이라 답할 수 없습니다."
MAJOR_ONLY_TEXT = "전공 강의자료는 해당 과목 수강생만 검색할 수 있습니다."


class UpstreamError(RuntimeError):
    """LLM·임베딩 공급사 장애. API가 503으로 바꾸고 한도를 되돌린다."""


@dataclass(frozen=True)
class PipelineDeps:
    session: Session
    embed_query: Callable[[str], Sequence[float]]
    llm: Any
    settings: Settings
    today: Callable[[], date] = seoul_today


def merge_hits(hits: Sequence[ChunkHit], *, k: int) -> list[ChunkHit]:
    best: dict[int, ChunkHit] = {}
    for h in hits:
        if h.chunk_id not in best or h.score > best[h.chunk_id].score:
            best[h.chunk_id] = h
    return sorted(best.values(), key=lambda h: (-h.score, h.chunk_id))[:k]


async def answer_question(question: str, user: UserContext, deps: PipelineDeps, *, mode: str = "baseline") -> Answer:
    question = question.strip()
    if not question:
        raise ValueError("질문이 비어 있습니다")
    if mode not in MODES:
        raise ValueError(f"mode는 {MODES} 중 하나: {mode!r}")
    s = deps.settings
    intent: str | None = None
    intent_valid: bool | None = None
    wanted: tuple[str, ...] | None = None  # None = 보이는 도구 전부 (baseline)
    notices: list[str] = []

    if mode == "workflow":
        c = await anyio.to_thread.run_sync(
            lambda: classify(deps.llm, question, model=s.classify_model, max_tokens=s.classify_max_tokens))
        intent, intent_valid = c.intent, c.valid
        p = plan(intent, user)
        wanted, notices = p.tools, list(p.notices)
        if not wanted:
            text = MAJOR_ONLY_TEXT if NEEDS_ENROLLMENT in notices else OUT_OF_SCOPE_TEXT
            return Answer(text=text, sources=[], citation_ok=True, notices=notices,
                          intent=intent, intent_valid=intent_valid)

    cache: dict[str, Sequence[float]] = {}

    def embed_once(query: str) -> Sequence[float]:
        if query not in cache:  # 도구가 여러 개여도 질문 임베딩은 한 번만 (설계 §5)
            cache[query] = deps.embed_query(query)
        return cache[query]

    server = build_server(user, deps.session, embed_once, k=s.search_k, min_score=s.search_min_score)
    hits: list[ChunkHit] = []
    async with connect(server) as client:
        visible = {tool.name for tool in (await client.list_tools()).tools}
        names = sorted(visible) if wanted is None else [n for n in wanted if n in visible]
        for name in names:
            try:
                hits.extend(parse_hits(await client.call_tool(name, {"query": question})))
            except ToolError:
                notices.append(f"tool_error:{name}")  # 도구 하나의 실패가 답변 전체를 막지 않게 한다
    today = deps.today()
    answer = await anyio.to_thread.run_sync(
        lambda: generate_answer(deps.llm, question, merge_hits(hits, k=s.search_k), model=s.generation_model,
                                effort=s.generation_effort, max_tokens=s.generation_max_tokens, today=today))
    return replace(answer, notices=notices + answer.notices, intent=intent, intent_valid=intent_valid)
```

주의: `evaluation/run.py`는 이 태스크에서 바꾸지 않는다(기본 `mode="baseline"`이라 동작 동일). 오늘 날짜 주입 때문에 **평가 결과가 기준선과 달라질 수 있다** → 튜터 작업 2에서 같은 코드로 `baseline-v2`를 다시 잰다.

- [ ] **Step 4: GREEN 확인** — `make check`
- [ ] **Step 5: 커밋** — `feat(core): workflow 모드(분류→처리 표), 도구 실패 격리, 오늘 날짜 주입`

---

### Task 5: 로그인·질문 API

**Files:**
- Create: `backend/app/api/deps.py`, `backend/app/api/routes.py`
- Modify: `backend/app/main.py`, `docs/generated/openapi.json`(`make generate`)
- Test: `backend/tests/db/test_api.py`

**Interfaces:**
- Consumes: Task 1 저장소, Task 2 `verify_password`·`issue_token`·`decode_token`·`seoul_today`, Task 4 `answer_question`·`UpstreamError`·`PipelineDeps`
- Produces: `POST /api/auth/login {username, password} → {access_token, token_type}`; `POST /api/ask {question} → {answer, sources[{file,page,section}], intent, notices}`; `AuthedUser(user_id, courses, daily_quota)`; 의존성 `get_session`, `current_user`, `get_answer_fn`(테스트에서 override)
- 오류: 401(토큰·로그인), 422(질문 비었거나 500자 초과), 429(한도), 503(상류 장애)

- [ ] **Step 1: 실패하는 테스트 작성** — `backend/tests/db/test_api.py`

```python
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_answer_fn, get_session
from app.core.answer import Answer, Source
from app.core.config import Settings, get_settings
from app.core.pipeline import UpstreamError
from app.core.security import hash_password, issue_token
from app.db.accounts import upsert_user
from app.db.models import User
from app.db.usage import used_on
from app.core.clock import seoul_today
from app.main import app

SECRET = "t" * 32


class FakeAnswerFn:
    def __init__(self, error: Exception | None = None):
        self.calls = []
        self.error = error

    async def __call__(self, question, user, session):
        self.calls.append((question, user))
        if self.error:
            raise self.error
        return Answer(text="답[1]", sources=[Source("academic/a.md", 2, "제목")], citation_ok=True,
                      notices=[], intent="academic", intent_valid=True)


@pytest.fixture
def api(session):
    fake = FakeAnswerFn()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, jwt_secret=SECRET)
    app.dependency_overrides[get_answer_fn] = lambda: fake
    yield TestClient(app), fake
    app.dependency_overrides.clear()


def make_account(session, *, courses=frozenset({"AGENT"}), quota=3, password="password123"):
    user = upsert_user(session, username="kim", password_hash=hash_password(password), courses=courses,
                       daily_quota=quota)
    session.commit()
    return user


def auth(user_id):
    return {"Authorization": f"Bearer {issue_token(user_id, secret=SECRET, ttl_hours=1)}"}


def test_login_returns_token_that_opens_ask(api, session):
    client, fake = api
    make_account(session)
    res = client.post("/api/auth/login", json={"username": "kim", "password": "password123"})
    assert res.status_code == 200 and res.json()["token_type"] == "bearer"
    ask = client.post("/api/ask", json={"question": "  수강신청?  "},
                      headers={"Authorization": f"Bearer {res.json()['access_token']}"})
    assert ask.status_code == 200
    assert ask.json() == {"answer": "답[1]", "sources": [{"file": "academic/a.md", "page": 2, "section": "제목"}],
                          "intent": "academic", "notices": []}
    question, user = fake.calls[0]
    assert question == "수강신청?" and user.courses == frozenset({"AGENT"})


def test_login_failures_are_indistinguishable(api, session):
    client, _ = api
    make_account(session)
    wrong = client.post("/api/auth/login", json={"username": "kim", "password": "nope-nope"})
    unknown = client.post("/api/auth/login", json={"username": "ghost", "password": "nope-nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_ask_requires_valid_token(api, session):
    client, fake = api
    assert client.post("/api/ask", json={"question": "q"}).status_code == 401
    assert client.post("/api/ask", json={"question": "q"}, headers={"Authorization": "Bearer junk"}).status_code == 401
    assert fake.calls == []


def test_ask_rejects_token_of_deleted_user(api, session):
    client, _ = api
    user = make_account(session)
    headers = auth(user.id)
    session.delete(session.get(User, user.id))
    session.commit()
    assert client.post("/api/ask", json={"question": "q"}, headers=headers).status_code == 401


def test_invalid_question_does_not_consume_quota(api, session):
    client, fake = api
    user = make_account(session)
    for bad in ("   ", "가" * 501):
        assert client.post("/api/ask", json={"question": bad}, headers=auth(user.id)).status_code == 422
    assert used_on(session, user.id, seoul_today()) == 0 and fake.calls == []


def test_quota_exhausted_returns_429(api, session):
    client, fake = api
    user = make_account(session, quota=1)
    assert client.post("/api/ask", json={"question": "q"}, headers=auth(user.id)).status_code == 200
    assert client.post("/api/ask", json={"question": "q"}, headers=auth(user.id)).status_code == 429
    assert len(fake.calls) == 1


def test_upstream_error_refunds_quota(api, session):
    client, fake = api
    fake.error = UpstreamError("anthropic down")
    user = make_account(session)
    res = client.post("/api/ask", json={"question": "q"}, headers=auth(user.id))
    assert res.status_code == 503
    assert used_on(session, user.id, seoul_today()) == 0


def test_guest_courses_come_from_db_not_token(api, session):
    client, fake = api
    user = make_account(session, courses=frozenset())
    client.post("/api/ask", json={"question": "q"}, headers=auth(user.id))
    assert fake.calls[0][1].courses == frozenset()
```

- [ ] **Step 2: RED 확인** — `make test`

- [ ] **Step 3: 구현** — `backend/app/api/deps.py`

```python
"""API 의존성 — 세션, 인증 사용자, 답변 함수. 테스트는 app.dependency_overrides로 바꾼다."""

from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from functools import lru_cache

import anthropic
import openai
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.answer import Answer, make_llm
from app.core.config import Settings, get_settings
from app.core.embeddings import OpenAIEmbedder
from app.core.pipeline import PipelineDeps, UpstreamError, answer_question
from app.core.security import InvalidToken, decode_token
from app.db.accounts import get_user, user_courses
from app.db.session import make_engine
from app.mcp.server import UserContext

AnswerFn = Callable[[str, UserContext, Session], Awaitable[Answer]]
_bearer = HTTPBearer(auto_error=False)
UNAUTHORIZED = HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다", {"WWW-Authenticate": "Bearer"})


@dataclass(frozen=True)
class AuthedUser:
    user_id: int
    courses: frozenset[str]
    daily_quota: int


@lru_cache
def _engine() -> Engine:
    return make_engine()


def get_session() -> Iterator[Session]:
    with Session(_engine()) as session:
        yield session


def current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AuthedUser:
    if cred is None:
        raise UNAUTHORIZED
    try:
        user_id = decode_token(cred.credentials, secret=settings.jwt_secret)
    except InvalidToken:
        raise UNAUTHORIZED from None
    user = get_user(session, user_id)
    if user is None:  # 토큰 발급 뒤 삭제된 계정
        raise UNAUTHORIZED
    return AuthedUser(user.id, user_courses(session, user.id), user.daily_quota)


@lru_cache
def _clients() -> tuple[OpenAIEmbedder, anthropic.Anthropic]:
    # 공급사 클라이언트는 프로세스당 하나. 설정은 프로세스 수명 동안 고정(Settings는 해시 불가라 인자로 받지 않는다)
    settings = get_settings()
    return OpenAIEmbedder.from_settings(settings), make_llm(settings)


def get_answer_fn(settings: Settings = Depends(get_settings)) -> AnswerFn:
    embedder, llm = _clients()

    async def answer_fn(question: str, user: UserContext, session: Session) -> Answer:
        deps = PipelineDeps(session=session, embed_query=lambda q: embedder.embed([q])[0], llm=llm, settings=settings)
        try:
            return await answer_question(question, user, deps, mode=settings.router_mode)
        except (anthropic.APIError, openai.APIError) as e:
            raise UpstreamError(type(e).__name__) from e

    return answer_fn
```


`backend/app/api/routes.py`

```python
"""HTTP 입출력 — 인증·한도·입력 검증·오류 변환만 한다. 답변은 주입된 answer_fn이 만든다."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, StringConstraints
from sqlalchemy.orm import Session

from app.api.deps import AnswerFn, AuthedUser, current_user, get_answer_fn, get_session
from app.core.clock import seoul_today
from app.core.config import Settings, get_settings
from app.core.pipeline import UpstreamError
from app.core.security import issue_token, verify_password
from app.db.accounts import find_user
from app.db.usage import consume_quota, refund_quota
from app.mcp.server import UserContext

QUESTION_MAX_CHARS = 500
router = APIRouter(prefix="/api")


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AskRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=QUESTION_MAX_CHARS)]


class SourceOut(BaseModel):
    file: str
    page: int
    section: str | None


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceOut]
    intent: str | None
    notices: list[str]


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, session: Session = Depends(get_session),
          settings: Settings = Depends(get_settings)) -> TokenResponse:
    user = find_user(session, body.username)
    if not verify_password(body.password, user.password_hash if user else None):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "아이디 또는 비밀번호가 올바르지 않습니다")
    return TokenResponse(access_token=issue_token(user.id, secret=settings.jwt_secret, ttl_hours=settings.jwt_ttl_hours))


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest, user: AuthedUser = Depends(current_user), session: Session = Depends(get_session),
              answer_fn: AnswerFn = Depends(get_answer_fn)) -> AskResponse:
    day = seoul_today()
    if not consume_quota(session, user.user_id, day, limit=user.daily_quota):
        session.rollback()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "오늘 질문 한도를 모두 사용했습니다")
    session.commit()
    try:
        answer = await answer_fn(body.question, UserContext(user.user_id, user.courses), session)
    except UpstreamError:
        refund_quota(session, user.user_id, day)
        session.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "답변 서비스가 잠시 응답하지 않습니다") from None
    return AskResponse(answer=answer.text, sources=[SourceOut(file=s.file, page=s.page, section=s.section)
                                                    for s in answer.sources],
                       intent=answer.intent, notices=answer.notices)
```

`backend/app/main.py`에 `from app.api.routes import router` 후 `app.include_router(router)`.

- [ ] **Step 4: `make generate`로 OpenAPI 스냅샷 갱신**
- [ ] **Step 5: GREEN 확인** — `make check`
- [ ] **Step 6: 커밋** — `feat(api): 로그인·질문 API — 401·422·429·503, 한도 되돌림`

---

### Task 6: 평가 — 모드와 의도 정확도

**Files:**
- Modify: `backend/evaluation/metrics.py`, `backend/evaluation/run.py`, `backend/evaluation/report.py`, `Makefile` (`eval` 타깃에 `MODE`)
- Test: `backend/tests/evaluation/test_metrics.py`, `test_run.py`, `test_report.py`

**Interfaces:**
- Consumes: Task 4 `answer_question(..., mode)`, `Answer.intent`·`intent_valid`; Task 3 `classify_prompt_hash`
- Produces: `intent_ok(item, answer) -> bool | None`; 실행 레코드 `intent`, `intent_valid`, `intent_ok`; meta `mode`, `classify_model`, `classify_prompt_hash`; 비교표 열 `모드`, `의도 정확도`

- [ ] **Step 1: 실패하는 테스트 추가**

`test_metrics.py` 끝에 (파일의 기존 `ITEM`·`NONE_ITEM` 사용, import에 `intent_ok` 추가):

```python
BOTH_ITEM = EvalItem("B01", "q", "both", (GoldSource("academic/a.pdf", 2),), ("k",))


def test_intent_ok_requires_valid_label():
    assert intent_ok(BOTH_ITEM, Answer("a", [], True, intent="both", intent_valid=True)) is True
    assert intent_ok(BOTH_ITEM, Answer("a", [], True, intent="both", intent_valid=False)) is False  # 형식 오류로 both 대체
    assert intent_ok(ITEM, Answer("a", [], True, intent="major", intent_valid=True)) is False


def test_intent_ok_is_none_for_baseline():
    assert intent_ok(ITEM, Answer("a", [], True)) is None


def test_none_handled_accepts_out_of_scope():
    answer = Answer("범위 밖", [], True, notices=["out_of_scope"], intent="none", intent_valid=True)
    assert none_handled(NONE_ITEM, answer) is True
```

`test_run.py`: 기존 `evaluate_item` 테스트 옆에 — workflow 답변이면 레코드에 `intent`, `intent_valid`, `intent_ok`가 들어가고 baseline 답변이면 `intent_ok`가 `None`임을 검사. `main(["--label", "x", "--mode", "nope"])`은 `SystemExit`(argparse `choices`).

`test_report.py`: 기존 `RECORDS`(intent 필드 없음)로 만든 행은 `모드`가 meta에 없으면 `—`, `의도 정확도`가 `—`. workflow 레코드(`intent_ok` True/False/True)면 `66.7%`.

- [ ] **Step 2: RED 확인** — `make test`

- [ ] **Step 3: 구현**

`metrics.py`:

```python
def intent_ok(item: EvalItem, answer: Answer) -> bool | None:
    """workflow 실행만 채점. 분류 형식 오류로 both가 된 경우는 맞아도 오답(설계 §5)."""
    if answer.intent is None:
        return None
    return bool(answer.intent_valid) and answer.intent == item.intent
```

`none_handled`의 공지 집합을 `{"no_evidence", "refused", "out_of_scope"}`로 넓힌다.

`run.py`:
- `evaluate_item` 레코드에 `"intent": answer.intent, "intent_valid": answer.intent_valid, "intent_ok": intent_ok(item, answer)` 추가.
- 인자 `--mode`(`choices=MODES`, 기본 `get_settings().router_mode`가 아니라 **`"baseline"`** — 평가 모드는 명시적으로 고른다).
- `answer_question(q, user, deps, mode=args.mode)`. 사용자 컨텍스트는 기존대로 **전 과목 수강**(권한이 의도 측정에 섞이지 않게).
- meta에 `"mode": args.mode, "classify_model": settings.classify_model, "classify_prompt_hash": classify_prompt_hash()`.
- 요약 출력에 `의도 {rate(r['intent_ok'] for r in records)}` 추가.

`report.py`:
- `summarize`에 `"mode": meta.get("mode", "—")`, `"intent_accuracy": rate(r.get("intent_ok") for r in records)`.
- 표 머리를 `| 실행 | 라벨 | 모드 | 프롬프트 | 문항 | 답변 정확도 (채점 수) | 의도 정확도 | recall@k | …`로, 행에 두 칸 추가(`_pct`는 `None`이면 `—`).

`Makefile`의 `eval` 타깃:

```make
	PYTHONPATH=backend $(PY) -m evaluation.run --label $(LABEL) $(if $(MODE),--mode $(MODE))
```

- [ ] **Step 4: GREEN 확인** — `make check`
- [ ] **Step 5: 커밋** — `feat(eval): workflow 모드 평가와 의도 정확도 지표`

---

### Task 7: 문서·위험 경로

**Files:**
- Modify: `docs/sot.md`, `AGENTS.md`, `docs/harness/risk-paths.txt`, `docs/design/2026-09-28-system-design.md`, `eval/README.md`
- Move: `docs/exec-plans/active/2026-09-29-m2-mcp-baseline.md` → `docs/exec-plans/done/`

- [ ] **Step 1: `docs/sot.md` 행 추가**

```markdown
| 의도 분류 프롬프트 | `backend/app/core/prompts/classify.md` | 평가 meta의 `classify_prompt_hash` | 실행 기록 |
| 처리 표 (의도 × 수강 여부 → 도구) | `backend/app/core/router.py` `plan()` | 설계 §5 표 | `tests/test_router.py` (게이트 1) |
| 계정·수강 과목 | DB `users`·`enrollments` (`make users`로만 변경) | 토큰은 user_id만 | `tests/db/test_api.py` |
```

- [ ] **Step 2: `AGENTS.md` 명령 표에 행 추가**

```markdown
| 계정 | `make users ARGS="add kim --courses AGENT,AWS"` | 비밀번호는 프롬프트로 입력. 과목 비우면 게스트(학사만) |
| 라우터 평가 | `make eval LABEL=router-v1 MODE=workflow` | 기본 MODE는 baseline |
```

- [ ] **Step 3: `docs/harness/risk-paths.txt`에 두 줄 추가** — `backend/app/api/`, `backend/app/core/security.py`
- [ ] **Step 4: 설계 정정** — §5 첫 줄 뒤에 `(분류 기본값 claude-haiku-4-5-20251001, 샘플링·effort 미사용)`, §6 표 4주차 행에 `기준선은 같은 코드로 baseline-v2 재측정(오늘 날짜 주입으로 생성 프롬프트가 바뀜)` 메모.
- [ ] **Step 5: `eval/README.md` 순서에** `4주차: make eval LABEL=baseline-v2 → make eval LABEL=router-v1 MODE=workflow → 둘 다 채점 → make eval-report` 추가.
- [ ] **Step 6: M2 계획을 done으로 이동**, 완료 기준 체크(`- [x] … — PR #5·#8·#9`).
- [ ] **Step 7: `make check` 후 커밋** — `docs: M3 SoT·명령·위험 경로·설계 정정`

---

## 튜터 작업 (구현 후, 사람)

1. `.env`에 `JWT_SECRET` (32자 이상 무작위, 예: `python -c "import secrets; print(secrets.token_urlsafe(48))"`) 추가. 에이전트는 `.env`를 열지 않는다.
2. 계정 만들기: `make users ARGS="add kim --courses AGENT,AWS,DB"`, 게스트 `make users ARGS="add guest --quota 20"`.
3. 같은 코드에서 두 번 측정: `make eval LABEL=baseline-v2` → `make eval LABEL=router-v1 MODE=workflow` (각 36회 생성 + router는 36회 분류, 유료).
4. 두 채점표 채점 → `make eval-report` → 비교표 커밋. 라우터 효과 = `router-v1` 대 `baseline-v2`(같은 생성 프롬프트).
5. 4주차 보고서: 의도 정확도, 분류 오답 사례, 라우터 전후 recall·출처 일치 변화 인용.

## 결정 로그

- 2026-09-30: 계획 작성. 설계 §8 M3 범위(로그인·JWT·CLI·일일 한도, classify/plan, `/api/ask`).
- 2026-09-30: **동기 Anthropic SDK 유지 + `anyio.to_thread`** — `AsyncAnthropic`로 바꾸면 `FakeLLM`·생성 테스트 전부가 한 번에 흔들린다. 이벤트 루프에서 동기 DB·임베딩 호출이 도는 것은 단일 서버·소수 사용자 규모에서 감수한다(M2 결정 로그의 AsyncAnthropic 계획을 대체).
- 2026-09-30: 분류기는 `messages.create` 기본 형태만 사용(Haiku 4.5에 effort·fallback beta 미검증). 형식 오류·거절 → `both` + `intent_valid=False`.
- 2026-09-30: `none` 의도는 LLM 없이 `OUT_OF_SCOPE_TEXT` + `out_of_scope` 공지. `none_handled`가 이 공지를 인정하도록 확장.
- 2026-09-30: 오늘 날짜(서울)를 생성 입력 앞에 주입(M2 이월, 지난 공지 대응). 생성 프롬프트가 바뀌므로 라우터 효과는 같은 코드의 `baseline-v2`와 비교한다.
- 2026-09-30: 한도는 `INSERT … ON CONFLICT … WHERE count < limit RETURNING` 한 문장, 0 한도는 코드에서 거부. 입력 검증 → 한도 → 답변, 503만 되돌림.
- 2026-09-30: M2 이월 처리 — 도구 실패 격리(Task 4), 빈 질문 거부(Task 4·5), 문자열 아닌 query 거부(Task 4), 공급사 오류 → 503(Task 5). MCP 내부 예외는 `ToolError`로만 다룬다.
```
