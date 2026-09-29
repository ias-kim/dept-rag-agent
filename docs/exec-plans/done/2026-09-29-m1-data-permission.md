# M1 데이터와 권한 바닥 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 스파이크 S로 남은 가정을 확인하고, PDF를 권한 메타데이터가 붙은 조각으로 적재해 두 번째 권한 겹(SQL 필터)이 걸린 벡터 검색까지 동작시킨다.

**Architecture:** 스키마는 Alembic 마이그레이션(원시 SQL)이 SoT이고, ORM 모델은 그 거울이다. 권한 일관성(스코프·과목)은 CHECK와 복합 FK로 **DB가** 강제한다. 적재는 `app/core/ingest`(추출 → 분할 → 임베딩 → 해시 동기화, 한 트랜잭션), 검색은 `app/db/search.py`의 `search_chunks`가 필수 키워드 인자 `allowed_courses`로 필터한다.

**Tech Stack:** Python 3.12, SQLAlchemy 2.1, Alembic 1.20, psycopg 3.3, pgvector 0.5(Python)/0.8.6(확장), pypdf 6.19, fpdf2 2.8(테스트 전용), OpenAI 임베딩 `text-embedding-3-small`

**Spec:** [`docs/design/2026-09-28-system-design.md`](../../design/2026-09-28-system-design.md) — §3 데이터 모델, §4 권한 겹 2, §8 단계 S·M1

## Global Constraints

- Python 3.12, 모든 의존성 `==` 고정(`backend/requirements.txt`, `requirements-dev.txt`).
- 계층 `api → core → mcp → db` 역방향 import 금지. `app.core.config`만 예외 (`tests/structural/test_layers.py`).
- `scope ∈ {'major','academic'}`, `(scope = 'major') = (course_code IS NOT NULL)`, 과목 코드는 대문자(`course_code = upper(course_code)`).
- `EMBEDDING_DIM = 1536`, 모델 `text-embedding-3-small`.
- `search_chunks`의 `allowed_courses`는 **기본값 없는 키워드 전용 인자**.
- 원본 PDF는 git에 올리지 않는다(`/data/` gitignore).
- 에이전트는 `.env`를 읽지 않는다.
- 각 태스크 끝에 `make check` 통과. DB 테스트는 `make db-up` 필요(CI는 서비스 컨테이너).
- 커밋 메시지는 한국어 conventional + `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **스캔 PDF(텍스트 없음)** — 조용히 빈 문서로 색인되면 안 된다. `SyncReport.empty`에 잡혀 CLI가 경고해야 한다 → Task 8 `test_empty_pdf_is_reported`.
2. **과목 폴더 없이 `data/major/x.pdf`에 놓인 PDF** — 적재 도중 IntegrityError가 아니라, **변경 전에** 위치를 알려주는 오류여야 한다 → Task 8 `test_misplaced_pdf_rejected_before_any_change`.
3. **임베딩 API가 중간에 실패** — 앞서 처리한 파일까지 포함해 색인이 반쯤 바뀐 상태로 남으면 안 된다 → Task 8 `test_embedder_failure_rolls_back_everything`.
4. **과목 코드 대소문자(`cs101` 폴더 vs `CS101` 수강)** — 같은 과목으로 취급되어야 한다 → Task 4 `test_course_code_must_be_uppercase`, Task 8 `test_course_folder_is_uppercased`.
5. **조각의 스코프·과목이 소속 문서와 다름** — 필터를 우회하는 조각이 생기면 안 된다 → Task 4 `test_chunk_scope_must_match_document`, `test_major_chunk_course_must_match_document`.

## 완료 기준

- [ ] 스파이크 3건 결과가 이 파일 "스파이크 결과"에 기록됨
- [x] 마이그레이션 0001로 5개 테이블·CHECK·복합 FK·부분 HNSW 2개 생성, 스키마 테스트 통과
- [x] 권한 테스트 행렬(설계 §4 중 DB 행) 통과
- [x] `make ingest`가 폴더 동기화(추가·갱신·삭제·변경 없음·빈 문서 경고), 한 트랜잭션
- [x] CI에서 DB 테스트가 실제로 실행됨(건너뛰지 않음) — PR #4 CI 73 passed, skip 0 (2026-09-29)
- [x] `docs/sot.md`의 청크 메타데이터·DB 구조 행이 실제 경로로 갱신, 이전 exec-plan(`2026-09-28-metadata-schema.md`)은 `done/`으로 이동

## 파일 구조

| 파일 | 책임 |
|---|---|
| `backend/app/core/config.py` | 설정(`Settings`, `get_settings`) — 어디서나 import 가능 |
| `backend/app/db/models.py` | ORM 모델 + `EMBEDDING_DIM`, `SCOPES` |
| `backend/app/db/session.py` | 엔진·세션 팩토리 |
| `backend/app/db/search.py` | `ChunkHit`, `search_chunks` (권한 겹 2) |
| `backend/alembic.ini`, `backend/migrations/env.py`, `backend/migrations/script.py.mako` | Alembic 설정 |
| `backend/migrations/versions/0001_initial_schema.py` | **DB 구조 SoT** |
| `backend/app/core/embeddings.py` | `Embedder` 프로토콜, `OpenAIEmbedder` |
| `backend/app/core/ingest/pdf.py` | `Page`, `extract_pages` |
| `backend/app/core/ingest/chunking.py` | `ChunkDraft`, `chunk_pages` |
| `backend/app/core/ingest/sync.py` | `SourceFile`, `SyncReport`, `discover`, `sync_folder` |
| `backend/app/core/ingest/__main__.py` | CLI `python -m app.core.ingest` |
| `backend/tests/fakes.py` | `unit`, `FakeEmbedder`, `make_pdf` 테스트 헬퍼 |
| `backend/tests/db/conftest.py` | 테스트 DB 생성·마이그레이션·정리 픽스처 |
| `backend/tests/db/test_schema.py`, `test_search_permissions.py`, `test_sync.py` | DB 테스트 |
| `backend/tests/ingest/test_pdf.py`, `test_chunking.py`, `backend/tests/test_embeddings.py` | 순수 테스트 |

---

## 스파이크 (S)

스파이크 코드는 **버린다**(스크래치 디렉터리에서 실행, 커밋 금지). 산출물은 아래 "스파이크 결과" 표 한 줄씩이다.

**사전 확인 완료 (2026-09-29, 계획 작성 중):** pgvector 확장 0.8.6에서 `WHERE scope=…` 부분 HNSW 인덱스 생성 OK, `(scope='major') = (course IS NOT NULL)` CHECK가 과목 없는 major 행을 IntegrityError로 차단. MCP 2.2: `FastMCP`는 `mcp.server.mcpserver.MCPServer`로 이름 변경, 저수준 `mcp.server.lowlevel.Server(name, on_list_tools=…, on_call_tool=…)`, 메모리 전송 `mcp.shared.memory.create_client_server_memory_streams()`.

### Task 1: S1 — MCP 2.2 메모리 전송으로 사용자별 도구 목록

**Files:** 스크래치 `probe_mcp.py` (커밋하지 않음)

- [ ] **Step 1: 프로브 작성**

```python
import anyio
from mcp import ClientSession, types
from mcp.server.lowlevel import Server
from mcp.shared.memory import create_client_server_memory_streams

SCHEMA = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}


def build_server(courses: frozenset[str]) -> Server:
    async def list_tools(ctx, params):
        tools = [types.Tool(name="search_academic", description="학사·공지 검색", inputSchema=SCHEMA)]
        if courses:
            tools.append(types.Tool(name="search_major", description="전공자료 검색", inputSchema=SCHEMA))
        return types.ListToolsResult(tools=tools)

    return Server("probe", on_list_tools=list_tools)


async def probe(courses: frozenset[str]) -> None:
    server = build_server(courses)
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        async with anyio.create_task_group() as tg:
            tg.start_soon(server.run, server_streams[0], server_streams[1], server.create_initialization_options())
            async with ClientSession(*client_streams) as client:
                await client.initialize()
                result = await client.list_tools()
                print(sorted(t.name for t in result.tools))
            tg.cancel_scope.cancel()


anyio.run(probe, frozenset())
anyio.run(probe, frozenset({"CS101"}))
```

- [ ] **Step 2: 실행**

Run: `backend/.venv/bin/python <scratch>/probe_mcp.py`
Expected: `['search_academic']` 다음 줄 `['search_academic', 'search_major']`. 필드명(`inputSchema`/`input_schema`)·`server.run` 인자·핸들러 시그니처가 다르면 오류 메시지를 따라 고치고, **고친 최종 형태**를 결과에 적는다.

- [ ] **Step 3: 결과 기록** — "스파이크 결과" 표 S1 행에 동작한 API 형태(서버 생성, 실행, 클라이언트 연결)를 적는다.

### Task 2: S2 — 임베딩 모델 차원 확인

**Files:** 스크래치 `probe_embed.py` (커밋하지 않음). **키 값은 출력하지 않는다.**

- [ ] **Step 1: 프로브 작성**

```python
from openai import OpenAI
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProbeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    openai_api_key: str


key = ProbeSettings().openai_api_key  # 값은 출력하지 않는다
resp = OpenAI(api_key=key).embeddings.create(model="text-embedding-3-small", input=["수강신청 정정 기간"])
print("dim", len(resp.data[0].embedding), "model", resp.model)
```

- [ ] **Step 2: 실행** — 레포 루트에서 Run: `backend/.venv/bin/python <scratch>/probe_embed.py` / Expected: `dim 1536`. 다르면 `EMBEDDING_DIM`과 마이그레이션의 `vector(1536)`을 그 값으로 바꾼다(Task 4 전에).
- [ ] **Step 3: 결과 기록** — S2 행.

### Task 3: S3 — 공용 계정에서 EC2용 IAM 역할 생성 가능 여부 (사람이 실행)

에이전트가 아니라 **튜터가** `StudentAdminAccess` SSO 세션으로 실행한다.

- [ ] **Step 1: 신뢰 정책 파일**

```bash
cat > /tmp/ec2-trust.json <<'EOF'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}
EOF
```

- [ ] **Step 2: 생성 → 확인 → 삭제**

```bash
aws iam create-role --role-name dept-rag-spike-role --assume-role-policy-document file:///tmp/ec2-trust.json --tags Key=Project,Value=dept-rag-agent Key=Owner,Value=Seonggwan
aws iam get-role --role-name dept-rag-spike-role --query Role.Arn
aws iam delete-role --role-name dept-rag-spike-role
```

Expected: ARN 출력 후 삭제 성공. `AccessDenied`면 메시지 전문(SCP 여부)을 기록 — M4 설계 변경 필요.

- [ ] **Step 3: 결과 기록** — S3 행.

### 스파이크 결과

| # | 질문 | 결과 | 설계 영향 |
|---|---|---|---|
| S0 | pgvector 부분 HNSW·CHECK | ✅ 0.8.6에서 동작 (2026-09-29) | 없음 |
| S1 | MCP 2.2 메모리 전송·사용자별 목록 | ✅ (2026-09-29) `Server(name, on_list_tools=, on_call_tool=)`(mcp.server.lowlevel), 핸들러 `async (ctx, params)` → `types.ListToolsResult(tools=[types.Tool(name, description, inputSchema=)])` / `types.CallToolResult(content=[types.TextContent(type="text", text=)])`(`params.name`·`params.arguments`), 실행 `tg.start_soon(server.run, server_streams[0], server_streams[1], server.create_initialization_options())`, 클라이언트 `ClientSession(*client_streams)`+`initialize()`(스트림은 `create_client_server_memory_streams()`) | 없음 — 요청마다 `build_server(courses)`로 서버를 만들고 클로저로 사용자 컨텍스트를 담으면 목록·호출 결과가 사용자별로 갈림(프로브로 확인) |
| S2 | 임베딩 차원 | ⏭ 생략 (Ruling 1) — OpenAIEmbedder가 차원 ≠ 1536이면 거부, 첫 실 적재에서 확인 | 실 적재 시 확인 |
| S3 | IAM 역할 생성 | ⏳ 튜터 실행 대기 | M4 전 확인 필요 |

---

## M1

### Task 4: 스키마 — 설정, 마이그레이션, 모델, 테스트 DB, CI

**Files:**
- Modify: `backend/requirements.txt`, `backend/requirements-dev.txt`, `docker/docker-compose.yml`, `Makefile`, `.github/workflows/check.yml`, `.gitignore`, `docs/harness/risk-paths.txt`
- Create: `backend/app/core/config.py`, `backend/app/db/models.py`, `backend/app/db/session.py`, `backend/alembic.ini`, `backend/migrations/env.py`, `backend/migrations/script.py.mako`, `backend/migrations/versions/0001_initial_schema.py`, `backend/tests/db/conftest.py`, `backend/tests/db/test_schema.py`

**Interfaces:**
- Produces: `Settings`, `get_settings() -> Settings`; `EMBEDDING_DIM: int = 1536`, `SCOPES = ("major", "academic")`; ORM `User, Enrollment, Document, Chunk, UsageDaily`; `make_engine(url: str | None = None) -> Engine`; pytest 픽스처 `db_url: str`, `engine: Engine`, `session: Session`

- [ ] **Step 1: 의존성 추가**

`backend/requirements.txt` 끝(빈 줄 위)에:

```
alembic==1.20.0
pypdf==6.19.0
```

`backend/requirements-dev.txt`에:

```
fpdf2==2.8.8
```

Run: `make setup` / Expected: 설치 성공.

- [ ] **Step 2: DB 헬스체크와 Make 타깃**

`docker/docker-compose.yml`의 `db` 서비스에 추가:

```yaml
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U dept_rag"]
      interval: 2s
      timeout: 3s
      retries: 30
```

`Makefile`의 `.PHONY`에 `db-up migrate ingest`를 추가하고 끝에:

```make
db-up:
	docker compose -f docker/docker-compose.yml up -d --wait

migrate:
	$(PY) -m alembic -c backend/alembic.ini upgrade head

ingest:
	PYTHONPATH=backend $(PY) -m app.core.ingest --root data
```

`.gitignore` 끝에:

```
# 원본 PDF (저작권·용량) — S3/로컬에만
/data/
```

- [ ] **Step 3: 실패하는 스키마 테스트 작성**

`backend/tests/db/conftest.py`:

```python
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parents[2]
DEFAULT_URL = "postgresql+psycopg://dept_rag:dept_rag@localhost:5433/dept_rag_test"
TABLES = "users, enrollments, documents, chunks, usage_daily"


@pytest.fixture(scope="session")
def db_url() -> str:
    url = make_url(os.environ.get("TEST_DATABASE_URL", DEFAULT_URL))
    admin = sa.create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{url.database}"')
            conn.exec_driver_sql(f'CREATE DATABASE "{url.database}"')
    except sa.exc.OperationalError as exc:
        pytest.fail(f"테스트 DB 연결 실패 → `make db-up` 후 다시 실행 ({exc.__class__.__name__})")
    finally:
        admin.dispose()
    rendered = url.render_as_string(hide_password=False)
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", rendered)
    command.upgrade(cfg, "head")
    return rendered


@pytest.fixture(scope="session")
def engine(db_url):
    eng = sa.create_engine(db_url)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s
        s.rollback()
    with engine.begin() as conn:
        conn.exec_driver_sql(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")
```

`backend/tests/db/test_schema.py`:

```python
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.db.models import EMBEDDING_DIM
from tests.fakes import unit

INSERT_DOC = "INSERT INTO documents (scope, course_code, path, sha256) VALUES (:s, :c, :p, :h) RETURNING id"
INSERT_CHUNK = (
    "INSERT INTO chunks (document_id, page, section, ord, text, embedding, scope, course_code) "
    "VALUES (:d, 1, NULL, 0, 't', CAST(:e AS vector), :s, :c)"
)


def add_doc(session, scope, course, path="a.pdf"):
    return session.execute(sa.text(INSERT_DOC), {"s": scope, "c": course, "p": path, "h": "0" * 64}).scalar_one()


def add_chunk(session, doc_id, scope, course):
    session.execute(sa.text(INSERT_CHUNK), {"d": doc_id, "e": str(unit(0)), "s": scope, "c": course})


@pytest.mark.parametrize("scope, course", [("major", None), ("academic", "CS101"), ("other", None)])
def test_document_scope_course_rule(session, scope, course):
    with pytest.raises(IntegrityError):
        add_doc(session, scope, course)


def test_course_code_must_be_uppercase(session):
    with pytest.raises(IntegrityError):
        add_doc(session, "major", "cs101")


def test_chunk_scope_must_match_document(session):
    doc = add_doc(session, "academic", None)
    with pytest.raises(IntegrityError):
        add_chunk(session, doc, "major", "CS101")


def test_major_chunk_course_must_match_document(session):
    doc = add_doc(session, "major", "CS101")
    with pytest.raises(IntegrityError):
        add_chunk(session, doc, "major", "CS202")


def test_deleting_document_cascades_to_chunks(session):
    doc = add_doc(session, "major", "CS101")
    add_chunk(session, doc, "major", "CS101")
    session.execute(sa.text("DELETE FROM documents WHERE id = :d"), {"d": doc})
    assert session.execute(sa.text("SELECT count(*) FROM chunks")).scalar_one() == 0


def test_embedding_dimension_matches_constant(session):
    typmod = session.execute(
        sa.text("SELECT atttypmod FROM pg_attribute WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'")
    ).scalar_one()
    assert typmod == EMBEDDING_DIM


def test_two_partial_vector_indexes(session):
    rows = session.execute(
        sa.text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'chunks' AND indexdef LIKE '%hnsw%'")
    ).all()
    defs = {name: d for name, d in rows}
    assert set(defs) == {"chunks_major_hnsw", "chunks_academic_hnsw"}
    assert "'major'" in defs["chunks_major_hnsw"] and "'academic'" in defs["chunks_academic_hnsw"]
```

`backend/tests/fakes.py` (이 태스크에서는 `unit`만, Task 7·8에서 확장):

```python
from app.db.models import EMBEDDING_DIM


def unit(i: int) -> list[float]:
    """i번 축만 1인 단위 벡터. 같은 i끼리 코사인 거리 0, 다른 i끼리 1."""
    v = [0.0] * EMBEDDING_DIM
    v[i % EMBEDDING_DIM] = 1.0
    return v
```

- [ ] **Step 4: RED 확인**

Run: `make db-up && make test`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.db.models'` (또는 alembic.ini 없음).

- [ ] **Step 5: 설정·모델·세션 구현**

`backend/app/core/config.py`:

```python
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://dept_rag:dept_rag@localhost:5433/dept_rag"
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    chunk_max_chars: int = 800
    chunk_overlap: int = 100
    data_dir: Path = Path("data")


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`backend/app/db/models.py`:

```python
"""ORM 모델 — DB 구조의 SoT는 migrations/. 제약(CHECK·FK)은 마이그레이션에만 있다."""

from datetime import date

from pgvector.sqlalchemy import Vector
from sqlalchemy import Date, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIM = 1536
SCOPES = ("major", "academic")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(Text)
    daily_quota: Mapped[int] = mapped_column(Integer, default=50)


class Enrollment(Base):
    __tablename__ = "enrollments"
    user_id: Mapped[int] = mapped_column(primary_key=True)
    course_code: Mapped[str] = mapped_column(String(32), primary_key=True)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(16))
    course_code: Mapped[str | None] = mapped_column(String(32))
    path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column()
    page: Mapped[int] = mapped_column()
    section: Mapped[str | None] = mapped_column(Text)
    ord: Mapped[int] = mapped_column()
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    scope: Mapped[str] = mapped_column(String(16))
    course_code: Mapped[str | None] = mapped_column(String(32))


class UsageDaily(Base):
    __tablename__ = "usage_daily"
    user_id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
```

`backend/app/db/session.py`:

```python
from sqlalchemy import Engine, create_engine

from app.core.config import get_settings


def make_engine(url: str | None = None) -> Engine:
    return create_engine(url or get_settings().database_url)
```

- [ ] **Step 6: Alembic 설정과 마이그레이션 0001**

`backend/alembic.ini`:

```ini
[alembic]
script_location = %(here)s/migrations
prepend_sys_path = %(here)s
sqlalchemy.url =
```

`backend/migrations/env.py`:

```python
from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings

url = context.config.get_main_option("sqlalchemy.url") or get_settings().database_url
connectable = engine_from_config({"sqlalchemy.url": url}, prefix="sqlalchemy.", poolclass=pool.NullPool)

with connectable.connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
```

`backend/migrations/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
"""

from alembic import op

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = None
depends_on = None


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

`backend/migrations/versions/0001_initial_schema.py`:

```python
"""초기 스키마 — 계정·수강·문서·조각·사용량. 설계 §3.

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UPGRADE = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    username      VARCHAR(64) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    daily_quota   INTEGER NOT NULL DEFAULT 50 CHECK (daily_quota >= 0)
);

CREATE TABLE enrollments (
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_code VARCHAR(32) NOT NULL CHECK (course_code = upper(course_code)),
    PRIMARY KEY (user_id, course_code)
);

CREATE TABLE documents (
    id          BIGSERIAL PRIMARY KEY,
    scope       VARCHAR(16) NOT NULL CHECK (scope IN ('major', 'academic')),
    course_code VARCHAR(32) CHECK (course_code = upper(course_code)),
    path        TEXT NOT NULL UNIQUE,
    sha256      CHAR(64) NOT NULL,
    CONSTRAINT documents_scope_course CHECK ((scope = 'major') = (course_code IS NOT NULL)),
    CONSTRAINT documents_id_scope UNIQUE (id, scope),
    CONSTRAINT documents_id_scope_course UNIQUE (id, scope, course_code)
);

CREATE TABLE chunks (
    id          BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL,
    page        INTEGER NOT NULL CHECK (page >= 1),
    section     TEXT,
    ord         INTEGER NOT NULL,
    text        TEXT NOT NULL,
    embedding   vector(1536) NOT NULL,
    scope       VARCHAR(16) NOT NULL,
    course_code VARCHAR(32),
    CONSTRAINT chunks_scope_course CHECK ((scope = 'major') = (course_code IS NOT NULL)),
    -- 조각의 스코프·과목은 소속 문서와 같아야 한다 (필터 우회 방지)
    CONSTRAINT chunks_doc_scope FOREIGN KEY (document_id, scope)
        REFERENCES documents (id, scope) ON DELETE CASCADE,
    CONSTRAINT chunks_doc_scope_course FOREIGN KEY (document_id, scope, course_code)
        REFERENCES documents (id, scope, course_code) ON DELETE CASCADE
);

CREATE INDEX chunks_document_id ON chunks (document_id);
CREATE INDEX chunks_major_hnsw ON chunks USING hnsw (embedding vector_cosine_ops) WHERE scope = 'major';
CREATE INDEX chunks_academic_hnsw ON chunks USING hnsw (embedding vector_cosine_ops) WHERE scope = 'academic';

CREATE TABLE usage_daily (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day     DATE NOT NULL,
    count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);
"""

DOWNGRADE = "DROP TABLE usage_daily, chunks, documents, enrollments, users;"


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
```

- [ ] **Step 7: GREEN 확인**

Run: `make test`
Expected: PASS (기존 19 + 스키마 테스트 전부).

- [ ] **Step 8: CI에 DB 서비스 추가**

`.github/workflows/check.yml`의 `gate1` 잡에 `runs-on` 아래로:

```yaml
    services:
      db:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: dept_rag
          POSTGRES_PASSWORD: dept_rag
          POSTGRES_DB: dept_rag
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U dept_rag"
          --health-interval 2s --health-timeout 3s --health-retries 30
    env:
      TEST_DATABASE_URL: postgresql+psycopg://dept_rag:dept_rag@localhost:5432/dept_rag_test
```

`docs/harness/risk-paths.txt`에 `backend/migrations/` 한 줄 추가.

- [ ] **Step 9: 전체 확인 후 커밋**

Run: `make check` / Expected: PASS

```bash
git add backend/requirements.txt backend/requirements-dev.txt docker/docker-compose.yml Makefile .gitignore \
  .github/workflows/check.yml docs/harness/risk-paths.txt backend/app/core/config.py backend/app/db/ \
  backend/alembic.ini backend/migrations/ backend/tests/fakes.py backend/tests/db/
git commit -m "feat(db): 초기 스키마 — 스코프·과목 CHECK, 복합 FK, 부분 HNSW 2종

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 5: 권한 겹 2 — `search_chunks`

**Files:**
- Create: `backend/app/db/search.py`, `backend/tests/db/test_search_permissions.py`

**Interfaces:**
- Consumes: `Chunk`, `Document`, `SCOPES` (Task 4), `session` 픽스처, `unit`
- Produces:

```python
@dataclass(frozen=True)
class ChunkHit:
    chunk_id: int; text: str; source: str; page: int; section: str | None
    scope: str; course_code: str | None; score: float

def search_chunks(session: Session, query_vec: Sequence[float], *, scope: str,
                  allowed_courses: Collection[str], k: int = 5, min_score: float = 0.0) -> list[ChunkHit]
```

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/db/test_search_permissions.py`:

```python
import pytest

from app.db.models import Chunk, Document
from app.db.search import search_chunks
from tests.fakes import unit


@pytest.fixture
def corpus(session):
    """학사 1, CS101 전공 1, CS202 전공 1 — 모두 같은 방향(unit(0)) + 학사 방향 다른 조각 1."""
    specs = [
        ("academic/a.pdf", "academic", None, 0),
        ("academic/b.pdf", "academic", None, 1),
        ("major/CS101/x.pdf", "major", "CS101", 0),
        ("major/CS202/y.pdf", "major", "CS202", 0),
    ]
    for path, scope, course, axis in specs:
        doc = Document(scope=scope, course_code=course, path=path, sha256="0" * 64)
        session.add(doc)
        session.flush()
        session.add(Chunk(document_id=doc.id, page=1, section=None, ord=0, text=path,
                          embedding=unit(axis), scope=scope, course_code=course))
    session.flush()


def sources(hits):
    return sorted(h.source for h in hits)


def test_enrolled_student_sees_only_own_course(session, corpus):
    hits = search_chunks(session, unit(0), scope="major", allowed_courses={"CS101"})
    assert sources(hits) == ["major/CS101/x.pdf"]


def test_no_enrollment_gets_no_major_chunks(session, corpus):
    assert search_chunks(session, unit(0), scope="major", allowed_courses=set()) == []


def test_foreign_course_request_returns_nothing(session, corpus):
    # MCP 계층이 교집합을 계산한 결과가 비었을 때와 같은 상황
    assert search_chunks(session, unit(0), scope="major", allowed_courses={"CS999"}) == []


def test_academic_is_open_to_everyone(session, corpus):
    hits = search_chunks(session, unit(0), scope="academic", allowed_courses=set())
    assert "academic/a.pdf" in sources(hits)
    assert all(h.scope == "academic" for h in hits)


def test_allowed_courses_is_required_keyword(session, corpus):
    with pytest.raises(TypeError):
        search_chunks(session, unit(0), scope="major")  # type: ignore[call-arg]


def test_min_score_drops_unrelated_chunks(session, corpus):
    hits = search_chunks(session, unit(0), scope="academic", allowed_courses=set(), min_score=0.5)
    assert sources(hits) == ["academic/a.pdf"]
    assert hits[0].score == pytest.approx(1.0)


def test_k_limits_results(session, corpus):
    assert len(search_chunks(session, unit(0), scope="academic", allowed_courses=set(), k=1)) == 1


def test_unknown_scope_rejected(session, corpus):
    with pytest.raises(ValueError):
        search_chunks(session, unit(0), scope="secret", allowed_courses=set())
```

- [ ] **Step 2: RED 확인** — Run: `make test` / Expected: FAIL `ModuleNotFoundError: No module named 'app.db.search'`

- [ ] **Step 3: 구현**

`backend/app/db/search.py`:

```python
"""권한 겹 2 — 모든 벡터 검색은 이 함수를 거친다. 설계 §4."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass

from sqlalchemy import and_, bindparam, or_, select
from sqlalchemy.orm import Session

from app.db.models import SCOPES, Chunk, Document


@dataclass(frozen=True)
class ChunkHit:
    chunk_id: int
    text: str
    source: str
    page: int
    section: str | None
    scope: str
    course_code: str | None
    score: float


def search_chunks(
    session: Session,
    query_vec: Sequence[float],
    *,
    scope: str,
    allowed_courses: Collection[str],
    k: int = 5,
    min_score: float = 0.0,
) -> list[ChunkHit]:
    if scope not in SCOPES:
        raise ValueError(f"unknown scope: {scope!r}")
    distance = Chunk.embedding.cosine_distance(list(query_vec)).label("distance")
    stmt = (
        select(Chunk, Document.path, distance)
        .join(Document, Chunk.document_id == Document.id)
        # 리터럴로 렌더링해야 플래너가 부분 인덱스(WHERE scope = '…')를 고를 수 있다
        .where(Chunk.scope == bindparam("scope", scope, literal_execute=True))
        # 권한 필터: 스코프 조건이 바뀌어도 이 줄이 전공 조각을 막는다
        .where(or_(Chunk.scope == "academic",
                   and_(Chunk.scope == "major", Chunk.course_code.in_(list(allowed_courses)))))
        .where(distance <= 1.0 - min_score)
        .order_by(distance)
        .limit(k)
    )
    return [
        ChunkHit(chunk_id=c.id, text=c.text, source=path, page=c.page, section=c.section,
                 scope=c.scope, course_code=c.course_code, score=1.0 - dist)
        for c, path, dist in session.execute(stmt)
    ]
```

- [ ] **Step 4: GREEN 확인** — Run: `make test` / Expected: PASS
- [ ] **Step 5: 커밋**

```bash
git add backend/app/db/search.py backend/tests/db/test_search_permissions.py
git commit -m "feat(db): 권한 필터가 걸린 search_chunks (권한 겹 2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 6: PDF 추출과 분할

**Files:**
- Create: `backend/app/core/ingest/__init__.py`(빈 파일), `backend/app/core/ingest/pdf.py`, `backend/app/core/ingest/chunking.py`, `backend/tests/ingest/test_pdf.py`, `backend/tests/ingest/test_chunking.py`
- Modify: `backend/tests/fakes.py` (`make_pdf` 추가)

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class Page: number: int; text: str
def extract_pages(path: Path) -> list[Page]

@dataclass(frozen=True)
class ChunkDraft: page: int; section: str | None; ord: int; text: str
def chunk_pages(pages: Sequence[Page], *, max_chars: int, overlap: int) -> list[ChunkDraft]

# tests/fakes.py
def make_pdf(path: Path, pages: Sequence[str]) -> Path   # ASCII 텍스트만 (Helvetica), 빈 문자열이면 빈 페이지
```

- [ ] **Step 1: `make_pdf` 헬퍼 추가** — `backend/tests/fakes.py` 전체를 아래로 교체:

```python
from collections.abc import Sequence
from pathlib import Path

from fpdf import FPDF

from app.db.models import EMBEDDING_DIM


def unit(i: int) -> list[float]:
    """i번 축만 1인 단위 벡터. 같은 i끼리 코사인 거리 0, 다른 i끼리 1."""
    v = [0.0] * EMBEDDING_DIM
    v[i % EMBEDDING_DIM] = 1.0
    return v


def make_pdf(path: Path, pages: Sequence[str]) -> Path:
    """테스트용 PDF. 한국어 폰트가 없으므로 ASCII만 쓴다. 빈 문자열이면 텍스트 없는 페이지."""
    pdf = FPDF()
    pdf.set_font("Helvetica", size=12)
    for text in pages:
        pdf.add_page()
        if text:
            pdf.multi_cell(0, 8, text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(pdf.output()))
    return path
```

- [ ] **Step 2: 실패하는 테스트 작성**

`backend/tests/ingest/test_pdf.py`:

```python
from app.core.ingest.pdf import Page, extract_pages
from tests.fakes import make_pdf


def test_extract_pages_numbers_from_one(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", ["Article 1 Purpose", "Article 2 Period"])
    assert extract_pages(pdf) == [Page(1, "Article 1 Purpose"), Page(2, "Article 2 Period")]


def test_blank_page_yields_empty_text(tmp_path):
    pdf = make_pdf(tmp_path / "b.pdf", [""])
    assert extract_pages(pdf) == [Page(1, "")]
```

`backend/tests/ingest/test_chunking.py`:

```python
import pytest

from app.core.ingest.chunking import ChunkDraft, chunk_pages
from app.core.ingest.pdf import Page


def test_short_page_is_one_chunk():
    assert chunk_pages([Page(3, "짧은 공지")], max_chars=800, overlap=100) == [
        ChunkDraft(page=3, section=None, ord=0, text="짧은 공지")
    ]


def test_long_page_splits_with_overlap():
    text = "".join(str(i % 10) for i in range(2000))
    drafts = chunk_pages([Page(1, text)], max_chars=800, overlap=100)
    assert [len(d.text) for d in drafts] == [800, 800, 600]
    assert drafts[0].text[-100:] == drafts[1].text[:100]
    assert [d.ord for d in drafts] == [0, 1, 2]


def test_empty_pages_skipped_and_ord_continues():
    drafts = chunk_pages([Page(1, "가"), Page(2, "   "), Page(3, "나")], max_chars=800, overlap=100)
    assert [(d.page, d.ord) for d in drafts] == [(1, 0), (3, 1)]


def test_article_heading_becomes_section_and_carries_over():
    pages = [Page(1, "학칙 안내\n제1조(목적) 이 규정은 수강신청을 정한다."), Page(2, "계속되는 내용")]
    drafts = chunk_pages(pages, max_chars=800, overlap=100)
    assert [d.section for d in drafts] == ["제1조(목적)", "제1조(목적)"]


def test_later_heading_replaces_section():
    pages = [Page(1, "제1조(목적) 가"), Page(2, "제2조(기간) 나")]
    assert [d.section for d in chunk_pages(pages, max_chars=800, overlap=100)] == ["제1조(목적)", "제2조(기간)"]


def test_overlap_must_be_smaller_than_max():
    with pytest.raises(ValueError):
        chunk_pages([Page(1, "가")], max_chars=100, overlap=100)
```

- [ ] **Step 3: RED 확인** — Run: `make test` / Expected: FAIL `ModuleNotFoundError: No module named 'app.core.ingest'`

- [ ] **Step 4: 구현**

`backend/app/core/ingest/pdf.py`:

```python
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass(frozen=True)
class Page:
    number: int
    text: str


def extract_pages(path: Path) -> list[Page]:
    reader = PdfReader(path)
    return [Page(i + 1, (page.extract_text() or "").strip()) for i, page in enumerate(reader.pages)]
```

`backend/app/core/ingest/chunking.py`:

```python
"""페이지 → 조각. 조각은 한 페이지 안에서만 만든다(출처 페이지가 하나로 정해지도록)."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.core.ingest.pdf import Page

SECTION_RE = re.compile(r"^\s*(제\s*\d+\s*조(?:\s*\([^)]*\))?)", re.MULTILINE)


@dataclass(frozen=True)
class ChunkDraft:
    page: int
    section: str | None
    ord: int
    text: str


def chunk_pages(pages: Sequence[Page], *, max_chars: int, overlap: int) -> list[ChunkDraft]:
    if not 0 <= overlap < max_chars:
        raise ValueError("overlap must be in [0, max_chars)")
    drafts: list[ChunkDraft] = []
    carried: str | None = None
    for page in pages:
        text = page.text.strip()
        if not text:
            continue
        headings = [(m.start(), m.group(1)) for m in SECTION_RE.finditer(text)]
        start = 0
        while start < len(text):
            end = min(start + max_chars, len(text))
            in_effect = [name for pos, name in headings if pos < end]
            section = in_effect[-1] if in_effect else carried
            drafts.append(ChunkDraft(page=page.number, section=section, ord=len(drafts), text=text[start:end]))
            if end == len(text):
                break
            start = end - overlap
        if headings:
            carried = headings[-1][1]
    return drafts
```

- [ ] **Step 5: GREEN 확인** — Run: `make test` / Expected: PASS
- [ ] **Step 6: 커밋**

```bash
git add backend/app/core/ingest/ backend/tests/ingest/ backend/tests/fakes.py
git commit -m "feat(ingest): PDF 페이지 추출과 조항 기반 분할

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 7: 임베딩

**Files:**
- Create: `backend/app/core/embeddings.py`, `backend/tests/test_embeddings.py`
- Modify: `backend/tests/fakes.py` (`FakeEmbedder` 추가)

**Interfaces:**
- Consumes: `EMBEDDING_DIM` (Task 4)
- Produces:

```python
class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

class OpenAIEmbedder:
    def __init__(self, client: Any, model: str, batch_size: int = 64) -> None
    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAIEmbedder"
    def embed(self, texts: Sequence[str]) -> list[list[float]]

# tests/fakes.py
class FakeEmbedder:  # .calls: int, .fail_on_call: int | None
    def embed(self, texts: Sequence[str]) -> list[list[float]]
```

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_embeddings.py`:

```python
from types import SimpleNamespace

import pytest

from app.core.embeddings import OpenAIEmbedder
from app.db.models import EMBEDDING_DIM


class FakeClient:
    def __init__(self, dim=EMBEDDING_DIM):
        self.dim = dim
        self.batches = []
        self.embeddings = SimpleNamespace(create=self._create)

    def _create(self, *, model, input):
        self.batches.append(list(input))
        return SimpleNamespace(data=[SimpleNamespace(embedding=[float(len(t))] * self.dim) for t in input])


def test_batches_and_preserves_order():
    client = FakeClient()
    texts = ["a" * (i % 5 + 1) for i in range(130)]
    vectors = OpenAIEmbedder(client, "m", batch_size=64).embed(texts)
    assert [len(b) for b in client.batches] == [64, 64, 2]
    assert [v[0] for v in vectors] == [float(len(t)) for t in texts]


def test_empty_input_makes_no_call():
    client = FakeClient()
    assert OpenAIEmbedder(client, "m").embed([]) == []
    assert client.batches == []


def test_wrong_dimension_is_rejected():
    with pytest.raises(ValueError, match="dimension"):
        OpenAIEmbedder(FakeClient(dim=3), "m").embed(["x"])
```

`backend/tests/fakes.py` 전체를 아래로 교체 (Task 6 내용 + `FakeEmbedder`):

```python
import zlib
from collections.abc import Sequence
from pathlib import Path

from fpdf import FPDF

from app.db.models import EMBEDDING_DIM


def unit(i: int) -> list[float]:
    """i번 축만 1인 단위 벡터. 같은 i끼리 코사인 거리 0, 다른 i끼리 1."""
    v = [0.0] * EMBEDDING_DIM
    v[i % EMBEDDING_DIM] = 1.0
    return v


def make_pdf(path: Path, pages: Sequence[str]) -> Path:
    """테스트용 PDF. 한국어 폰트가 없으므로 ASCII만 쓴다. 빈 문자열이면 텍스트 없는 페이지."""
    pdf = FPDF()
    pdf.set_font("Helvetica", size=12)
    for text in pages:
        pdf.add_page()
        if text:
            pdf.multi_cell(0, 8, text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(pdf.output()))
    return path


class FakeEmbedder:
    """텍스트 CRC로 축을 고르는 결정론적 임베더. fail_on_call번째 호출에서 예외."""

    def __init__(self, fail_on_call: int | None = None):
        self.calls = 0
        self.fail_on_call = fail_on_call

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        if self.fail_on_call is not None and self.calls == self.fail_on_call:
            raise RuntimeError("fake embedding failure")
        return [unit(zlib.crc32(t.encode())) for t in texts]
```

- [ ] **Step 2: RED 확인** — Run: `make test` / Expected: FAIL `ModuleNotFoundError: No module named 'app.core.embeddings'`

- [ ] **Step 3: 구현**

`backend/app/core/embeddings.py`:

```python
from collections.abc import Sequence
from typing import Any, Protocol

from app.core.config import Settings
from app.db.models import EMBEDDING_DIM


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    def __init__(self, client: Any, model: str, batch_size: int = 64) -> None:
        self._client = client
        self._model = model
        self._batch_size = batch_size

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAIEmbedder":
        from openai import OpenAI

        return cls(OpenAI(api_key=settings.openai_api_key), settings.embedding_model)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = list(texts[i : i + self._batch_size])
            response = self._client.embeddings.create(model=self._model, input=batch)
            vectors.extend(list(item.embedding) for item in response.data)
        for v in vectors:
            if len(v) != EMBEDDING_DIM:
                raise ValueError(f"embedding dimension {len(v)} != {EMBEDDING_DIM}")
        return vectors
```

- [ ] **Step 4: GREEN 확인** — Run: `make test` / Expected: PASS
- [ ] **Step 5: 커밋**

```bash
git add backend/app/core/embeddings.py backend/tests/test_embeddings.py backend/tests/fakes.py
git commit -m "feat(core): 배치 임베딩과 차원 검증

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 8: 해시 기반 폴더 동기화와 CLI

**Files:**
- Create: `backend/app/core/ingest/sync.py`, `backend/app/core/ingest/__main__.py`, `backend/tests/db/test_sync.py`

**Interfaces:**
- Consumes: `extract_pages`, `chunk_pages` (Task 6), `Embedder`, `OpenAIEmbedder.from_settings` (Task 7), `Document`, `Chunk` (Task 4), `make_engine`, `get_settings`
- Produces:

```python
@dataclass(frozen=True)
class SourceFile: rel_path: str; abs_path: Path; scope: str; course_code: str | None

@dataclass
class SyncReport:
    added: list[str]; updated: list[str]; removed: list[str]; unchanged: list[str]; empty: list[str]
    def summary(self) -> str

def discover(root: Path) -> list[SourceFile]          # 잘못된 위치면 ValueError (변경 전)
def sync_folder(session: Session, root: Path, embedder: Embedder, *, max_chars: int, overlap: int) -> SyncReport
```

폴더 규칙: `root/academic/**.pdf` → 학사, `root/major/<과목코드>/**.pdf` → 전공(과목 코드는 대문자로). 그 외 위치의 PDF는 오류, PDF가 아닌 파일은 무시.

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/db/test_sync.py`:

```python
import pytest
from sqlalchemy import func, select

from app.core.ingest.sync import sync_folder
from app.db.models import Chunk, Document
from tests.fakes import FakeEmbedder, make_pdf

OPTS = {"max_chars": 800, "overlap": 100}


@pytest.fixture
def root(tmp_path):
    make_pdf(tmp_path / "academic" / "calendar.pdf", ["Registration Sep 8", "Grades Dec 20"])
    make_pdf(tmp_path / "academic" / "rules.pdf", ["Article 1 Purpose"])
    make_pdf(tmp_path / "major" / "cs101" / "lec1.pdf", ["Stacks and queues"])
    return tmp_path


def chunk_count(session, path=None):
    stmt = select(func.count()).select_from(Chunk).join(Document, Chunk.document_id == Document.id)
    if path:
        stmt = stmt.where(Document.path == path)
    return session.execute(stmt).scalar_one()


def test_first_sync_adds_everything(session, root):
    report = sync_folder(session, root, FakeEmbedder(), **OPTS)
    assert sorted(report.added) == ["academic/calendar.pdf", "academic/rules.pdf", "major/cs101/lec1.pdf"]
    assert chunk_count(session) == 4


def test_course_folder_is_uppercased(session, root):
    sync_folder(session, root, FakeEmbedder(), **OPTS)
    doc = session.scalars(select(Document).where(Document.path == "major/cs101/lec1.pdf")).one()
    assert (doc.scope, doc.course_code) == ("major", "CS101")


def test_second_sync_is_noop_without_embedding(session, root):
    sync_folder(session, root, FakeEmbedder(), **OPTS)
    embedder = FakeEmbedder()
    report = sync_folder(session, root, embedder, **OPTS)
    assert len(report.unchanged) == 3 and not (report.added or report.updated or report.removed)
    assert embedder.calls == 0


def test_changed_file_replaces_its_chunks(session, root):
    sync_folder(session, root, FakeEmbedder(), **OPTS)
    make_pdf(root / "academic" / "rules.pdf", ["Article 1 Purpose", "Article 2 Scope", "Article 3 Terms"])
    report = sync_folder(session, root, FakeEmbedder(), **OPTS)
    assert report.updated == ["academic/rules.pdf"]
    assert chunk_count(session, "academic/rules.pdf") == 3


def test_deleted_file_removes_chunks(session, root):
    sync_folder(session, root, FakeEmbedder(), **OPTS)
    (root / "academic" / "calendar.pdf").unlink()
    report = sync_folder(session, root, FakeEmbedder(), **OPTS)
    assert report.removed == ["academic/calendar.pdf"]
    assert chunk_count(session, "academic/calendar.pdf") == 0


def test_empty_pdf_is_reported(session, root):
    make_pdf(root / "academic" / "scan.pdf", [""])
    report = sync_folder(session, root, FakeEmbedder(), **OPTS)
    assert report.empty == ["academic/scan.pdf"]
    assert "scan.pdf" in report.summary()


def test_misplaced_pdf_rejected_before_any_change(session, root):
    make_pdf(root / "major" / "loose.pdf", ["No course folder"])
    with pytest.raises(ValueError, match="major/loose.pdf"):
        sync_folder(session, root, FakeEmbedder(), **OPTS)
    assert session.execute(select(func.count()).select_from(Document)).scalar_one() == 0


def test_embedder_failure_rolls_back_everything(session, root):
    with pytest.raises(RuntimeError):
        sync_folder(session, root, FakeEmbedder(fail_on_call=2), **OPTS)
    assert session.execute(select(func.count()).select_from(Document)).scalar_one() == 0
    assert chunk_count(session) == 0


def test_non_pdf_files_are_ignored(session, root):
    (root / "academic" / ".DS_Store").write_bytes(b"x")
    report = sync_folder(session, root, FakeEmbedder(), **OPTS)
    assert len(report.added) == 3
```

- [ ] **Step 2: RED 확인** — Run: `make test` / Expected: FAIL `ModuleNotFoundError: No module named 'app.core.ingest.sync'`

- [ ] **Step 3: 구현**

`backend/app/core/ingest/sync.py`:

```python
"""폴더(→ 나중에 S3) ↔ 색인 동기화. 해시가 같으면 건너뛰고, 전체를 한 트랜잭션으로 처리한다. 설계 결정 11."""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.embeddings import Embedder
from app.core.ingest.chunking import chunk_pages
from app.core.ingest.pdf import extract_pages
from app.db.models import Chunk, Document


@dataclass(frozen=True)
class SourceFile:
    rel_path: str
    abs_path: Path
    scope: str
    course_code: str | None


@dataclass
class SyncReport:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    empty: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"추가 {len(self.added)} · 갱신 {len(self.updated)} · 삭제 {len(self.removed)} · 변경 없음 {len(self.unchanged)}"
        ]
        if self.empty:
            lines.append("⚠️ 텍스트 없음(스캔 PDF?): " + ", ".join(self.empty))
        return "\n".join(lines)


def discover(root: Path) -> list[SourceFile]:
    files: list[SourceFile] = []
    misplaced: list[str] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() != ".pdf":
            continue
        rel = p.relative_to(root)
        parts = rel.parts
        if parts[0] == "academic":
            files.append(SourceFile(rel.as_posix(), p, "academic", None))
        elif parts[0] == "major" and len(parts) >= 3:
            files.append(SourceFile(rel.as_posix(), p, "major", parts[1].upper()))
        else:
            misplaced.append(rel.as_posix())
    if misplaced:
        raise ValueError(
            "위치가 잘못된 PDF (academic/… 또는 major/<과목코드>/…): " + ", ".join(misplaced)
        )
    return files


def sync_folder(session: Session, root: Path, embedder: Embedder, *, max_chars: int, overlap: int) -> SyncReport:
    sources = discover(root)  # 잘못된 위치면 여기서 끝 — DB 변경 없음
    report = SyncReport()
    try:
        existing = {d.path: d for d in session.scalars(select(Document))}
        seen: set[str] = set()
        for sf in sources:
            seen.add(sf.rel_path)
            sha = hashlib.sha256(sf.abs_path.read_bytes()).hexdigest()
            old = existing.get(sf.rel_path)
            if old is not None and (old.sha256, old.scope, old.course_code) == (sha, sf.scope, sf.course_code):
                report.unchanged.append(sf.rel_path)
                continue
            drafts = chunk_pages(extract_pages(sf.abs_path), max_chars=max_chars, overlap=overlap)
            vectors = embedder.embed([d.text for d in drafts]) if drafts else []
            if old is not None:
                session.delete(old)
                session.flush()  # 같은 path로 다시 넣기 전에 삭제를 먼저 반영
            doc = Document(scope=sf.scope, course_code=sf.course_code, path=sf.rel_path, sha256=sha)
            session.add(doc)
            session.flush()
            session.add_all(
                Chunk(document_id=doc.id, page=d.page, section=d.section, ord=d.ord, text=d.text,
                      embedding=v, scope=sf.scope, course_code=sf.course_code)
                for d, v in zip(drafts, vectors, strict=True)
            )
            (report.updated if old is not None else report.added).append(sf.rel_path)
            if not drafts:
                report.empty.append(sf.rel_path)
        for path, doc in existing.items():
            if path not in seen:
                session.delete(doc)
                report.removed.append(path)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return report
```

`backend/app/core/ingest/__main__.py`:

```python
import argparse
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.embeddings import OpenAIEmbedder
from app.core.ingest.sync import sync_folder
from app.db.session import make_engine


def main(argv: list[str] | None = None) -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(prog="python -m app.core.ingest")
    parser.add_argument("--root", type=Path, default=settings.data_dir)
    args = parser.parse_args(argv)
    with Session(make_engine()) as session:
        report = sync_folder(
            session, args.root, OpenAIEmbedder.from_settings(settings),
            max_chars=settings.chunk_max_chars, overlap=settings.chunk_overlap,
        )
    print(report.summary())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: GREEN 확인** — Run: `make test` / Expected: PASS
- [ ] **Step 5: 실제 자료 스모크 (사람 확인)** — `data/academic/`에 실제 공지 PDF 1~2개를 두고 `make migrate && make ingest`. Expected: `추가 N …` 출력, 한국어 텍스트가 조각에 들어갔는지 `psql`로 `SELECT page, section, left(text, 60) FROM chunks LIMIT 5;` 확인. 스캔 PDF 경고가 뜨면 exec-plan 결정 로그에 기록.
- [ ] **Step 6: 커밋**

```bash
git add backend/app/core/ingest/sync.py backend/app/core/ingest/__main__.py backend/tests/db/test_sync.py
git commit -m "feat(ingest): 해시 기반 폴더 동기화와 make ingest

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 9: 문서 갱신과 마무리

**Files:**
- Modify: `docs/sot.md`, `AGENTS.md`, `docs/exec-plans/active/2026-09-28-metadata-schema.md` → `docs/exec-plans/done/`, 이 파일 → `docs/exec-plans/done/`

- [ ] **Step 1: `docs/sot.md` 두 행 교체**

```markdown
| 청크 메타데이터 스키마 (`source`·`page`·`section`·`scope`·`course`) | `backend/migrations/versions/0001_initial_schema.py` (`documents.path`, `chunks.page/section/scope/course_code`) | 출처 표시, 검색 필터, 평가셋 | `tests/db/test_schema.py` (게이트 1) |
| DB 구조 | `backend/migrations/` (Alembic) | `backend/app/db/models.py` | `tests/db/test_schema.py` (차원·인덱스) |
```

- [ ] **Step 2: `AGENTS.md` 명령 표에 두 행 추가, 테스트 행 비고 수정**

```markdown
| DB 기동 | `make db-up` | `make test`/`make check` 전에 필요 (CI는 서비스 컨테이너) |
| 적재 | `make migrate && make ingest` | `data/academic/…`, `data/major/<과목코드>/…` PDF |
```

- [ ] **Step 3: exec-plan 이동** — 이전 계획의 결정 로그에 `- 2026-09-29: M1 계획(2026-09-29-m1-data-permission.md)으로 대체되어 완료 처리.` 한 줄을 추가하고 두 파일을 `docs/exec-plans/done/`으로 `git mv`.

- [ ] **Step 4: 최종 확인** — Run: `make check` / Expected: PASS. 게이트 2: `reviewer` 서브에이전트에 이 계획의 완료 기준으로 판정 요청. 게이트 3: `backend/migrations/`, `.github/`, `docker/` 변경이므로 Codex 교차 리뷰.

- [ ] **Step 5: 커밋과 PR**

```bash
git add -A docs AGENTS.md
git commit -m "docs: M1 완료 — SoT 경로 갱신, exec-plan 이동

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push -u origin feat/m1-data-permission
```

---

## 실행 전제

1. `chore/deps-upgrade` PR 병합 (이 계획은 fastapi 0.141 / mcp 2.2 / sqlalchemy 2.1 기준).
2. `docs/system-design` PR(설계 + 이 계획) 병합.
3. `git switch main && git pull && git switch -c feat/m1-data-permission`.

## 결정 로그

- 2026-09-29: 계획 작성. 스키마는 원시 SQL 마이그레이션을 SoT로, ORM은 제약 없이 거울로 둔다(두 곳에 제약을 쓰면 어긋남).
- 2026-09-29: 조각↔문서 스코프·과목 일치를 트리거 대신 복합 FK(`MATCH SIMPLE`)로 강제. 학사 조각은 과목이 NULL이라 과목 FK는 검사되지 않지만 스코프 FK가 덮는다.
- 2026-09-29: 설계 §3의 `usage_daily.date`는 컬럼명을 `day`로 한다(타입명과 혼동 방지).
- 2026-09-29: 로컬 DB 호스트 포트를 5433으로 변경 — 5432는 다른 프로젝트 컨테이너가 사용 중. CI는 5432 유지.
