# M2 MCP 도구와 기준선 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 요청마다 사용자 컨텍스트를 넣은 MCP 서버(검색 도구 2종, 권한 겹 1)와 출처를 코드가 검증하는 답변 생성을 만들고, 라우터 없는 기준선을 평가셋으로 측정할 수 있게 한다.

**Architecture:** `app/mcp/server.py`가 `UserContext`를 클로저로 품은 저수준 MCP `Server`를 만들고 `list_tools`에서 도구를 거르며 `call_tool`에서 M1의 `search_chunks`(권한 겹 2)를 부른다. `app/core/pipeline.py`는 같은 프로세스 메모리 전송으로 연결해, 보이는 도구를 모두 호출한 뒤(기준선 = 라우터 없음) `app/core/answer.py`로 답을 만들고 인용 ID를 검증해 출처를 조각 메타데이터로 조립한다. `backend/evaluation/`은 평가셋 로드·동결 검사·지표·실행·비교표를 맡는다.

**Tech Stack:** Python 3.12, mcp 2.2.0 (저수준 `Server`, `create_client_server_memory_streams`), anthropic 1.8.0 (`client.beta.messages.create`), anyio(pytest 플러그인), PyYAML, M1의 SQLAlchemy/pgvector 스택

**Spec:** [`docs/design/2026-09-28-system-design.md`](../../design/2026-09-28-system-design.md) — §2 흐름, §4 권한 겹 1, §5 생성·출처 검증, §6 평가, §8 M2

## Global Constraints

- Python 3.12, 모든 의존성 `==` 고정. 계층 `api → core → mcp → db` 역방향 import 금지(`app.core.config`만 예외) — `app/mcp`는 `app/core`를 import하지 않는다(임베딩은 호출 가능 객체로 주입).
- **사용자 역할·수강 과목은 서버 코드가 `UserContext`로만 전달한다. LLM 프롬프트·도구 인자로 받지 않는다.** 도구 인자 `course_code`는 범위를 좁히기만 한다(교집합).
- `search_chunks(..., allowed_courses=...)`에는 항상 `frozenset`을 넘긴다(M1: `str`이면 `TypeError`).
- 답변 생성 모델은 설정값 `generation_model = "claude-sonnet-5-5"`, `generation_effort = "medium"`, `generation_max_tokens = 4096`. **`temperature`/`top_p`/`top_k`는 보내지 않는다**(Sonnet 5.5는 기본값이 아닌 샘플링 값에 400). 거절 대비 `client.beta.messages.create(..., betas=["server-side-fallback-2026-07-01"], fallbacks="default")`.
- `stop_reason == "refusal"`이면 `content`를 읽지 않는다.
- 출처 문자열(파일·페이지·조항)은 LLM 텍스트가 아니라 `ChunkHit` 메타데이터로 코드가 만든다. 검색되지 않은 조각 ID 인용은 제거하고 `citation_ok=False`.
- 테스트는 실제 Anthropic/OpenAI API를 호출하지 않는다. 에이전트는 `.env`를 열거나 출력하지 않는다.
- **레포가 PUBLIC** — 강의자료 원문이 섞이는 `eval/runs/`, `eval/grading/`은 git에 올리지 않는다(집계된 `docs/generated/eval-comparison.md`만 커밋).
- 로컬 테스트 DB 포트 5433. 커밋: 한국어 conventional + `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. 각 태스크 끝에 `make check` 통과.

## Review Focus

1. **LLM이 검색되지 않은 조각 ID(`[C99]`)를 인용** — 화면 출처에 절대 나타나면 안 된다 → Task 2 `test_unretrieved_citation_is_dropped`.
2. **수강 과목 없는 사용자가 목록에 없는 `search_major`를 직접 호출** — 데이터 없이 오류여야 한다 → Task 1 `test_hidden_tool_call_is_rejected`.
3. **도구 인자 `course_code`로 미수강 과목을 요청** — 빈 결과여야 한다(넓히기 불가) → Task 1 `test_course_code_argument_cannot_widen`.
4. **기준 점수를 넘는 조각이 없음** — LLM을 부르지 않고 "자료 없음" 안내 → Task 3 `test_no_hits_skips_llm`.
5. **동결 후 평가셋 수정** — 게이트 1이 실패해야 비교표가 성립 → Task 4 `test_check_frozen_rejects_changed_file`.

## 완료 기준

- [ ] MCP 서버: 역할별 도구 목록, 숨긴 도구 호출 거부, `course_code` 교집합 — 테스트 통과
- [ ] 답변 생성: 인용 검증·번호 재부여·출처 조립·거절 처리 — 실제 API 없이 테스트 통과
- [ ] 기준선 파이프라인: 권한 안에서 모든 도구 호출 → 병합 → 생성, 조각 없으면 LLM 미호출
- [ ] 평가: 평가셋 검증·동결 검사(게이트 1), 지표, `make eval`·`make eval-report`·`make eval-freeze`
- [ ] 문서: SoT·AGENTS·설계(temperature 정정)·평가 가이드
- [ ] (튜터) 평가셋 36문항 작성 → 동결 → 실제 적재 → 기준선 측정 → 채점 → 비교표

## 파일 구조

| 파일 | 책임 |
|---|---|
| `backend/app/mcp/server.py` | `UserContext`, `visible_tools`, `build_server` (권한 겹 1) |
| `backend/app/mcp/connection.py` | `connect`(메모리 전송 클라이언트), `parse_hits`, `ToolError` |
| `backend/app/core/prompts/answer.md` | 답변 생성 시스템 프롬프트 (**프롬프트 SoT**) |
| `backend/app/core/answer.py` | `Source`, `Answer`, `generate_answer`, `verify_citations`, `render_context`, `prompt_hash`, `make_llm` |
| `backend/app/core/pipeline.py` | `PipelineDeps`, `answer_question`(기준선), `merge_hits` |
| `backend/evaluation/dataset.py` | `EvalItem`, `load_items`, `sha256_of`, `check_frozen`, 동결 CLI |
| `backend/evaluation/metrics.py` | `recall_at_k`, `source_match`, `none_handled`, `rate` |
| `backend/evaluation/run.py` | `evaluate_item`, `run_items`, `write_run`, CLI(`make eval`) |
| `backend/evaluation/report.py` | 실행·채점 집계 → `docs/generated/eval-comparison.md` |
| `eval/README.md`, `eval/RUBRIC.md` | 평가셋 작성·채점 가이드 |

---

### Task 1: MCP 서버 — 권한 겹 1

**Files:**
- Create: `backend/app/mcp/server.py`, `backend/app/mcp/connection.py`, `backend/tests/db/test_mcp_server.py`
- Modify: `backend/tests/conftest.py` (`anyio_backend` 픽스처), `backend/tests/fakes.py` (`seed_chunks` 추가 — 파일 전체 교체)

**Interfaces:**
- Consumes: `search_chunks(session, query_vec, *, scope, allowed_courses, k, min_score) -> list[ChunkHit]`, `ChunkHit`(chunk_id, text, source, page, section, scope, course_code, score), `Document`, `Chunk`, `unit`
- Produces:

```python
@dataclass(frozen=True)
class UserContext: user_id: int; courses: frozenset[str]
TOOL_ACADEMIC = "search_academic"; TOOL_MAJOR = "search_major"
def visible_tools(user: UserContext) -> list[types.Tool]
def build_server(user: UserContext, session: Session, embed_query: Callable[[str], Sequence[float]], *, k: int, min_score: float) -> Server
# connection.py
class ToolError(RuntimeError): ...
@asynccontextmanager
async def connect(server: Server) -> AsyncIterator[ClientSession]
def parse_hits(result: types.CallToolResult) -> list[ChunkHit]
# tests/fakes.py
def seed_chunks(session: Session, specs: Sequence[tuple[str, str, str | None, int]]) -> None  # (path, scope, course, axis)
```

- [ ] **Step 1: 테스트 기반 준비**

`backend/tests/conftest.py` 끝에 추가:

```python


@pytest.fixture
def anyio_backend():
    return "asyncio"
```

`backend/tests/fakes.py` 전체를 아래로 교체(기존 `unit`, `make_pdf`, `FakeEmbedder`는 그대로 두고 `seed_chunks`만 추가):

```python
import zlib
from collections.abc import Sequence
from pathlib import Path

from fpdf import FPDF
from sqlalchemy.orm import Session

from app.db.models import EMBEDDING_DIM, Chunk, Document


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


def seed_chunks(session: Session, specs: Sequence[tuple[str, str, str | None, int]]) -> None:
    """(path, scope, course_code, axis)마다 문서 1개·조각 1개를 넣는다. 조각 임베딩은 unit(axis)."""
    for path, scope, course, axis in specs:
        doc = Document(scope=scope, course_code=course, path=path, sha256="0" * 64)
        session.add(doc)
        session.flush()
        session.add(Chunk(document_id=doc.id, page=1, section=None, ord=0, text=f"{path} 본문",
                          embedding=unit(axis), scope=scope, course_code=course))
    session.flush()
```

> 기존 `fakes.py`와 `unit`/`make_pdf`/`FakeEmbedder` 본문이 다르면 **기존 본문을 유지**하고 import와 `seed_chunks`만 추가한다.

- [ ] **Step 2: 실패하는 테스트 작성** — `backend/tests/db/test_mcp_server.py`:

```python
import pytest

from app.mcp.connection import ToolError, connect, parse_hits
from app.mcp.server import TOOL_ACADEMIC, TOOL_MAJOR, UserContext, build_server
from tests.fakes import seed_chunks, unit

pytestmark = pytest.mark.anyio

CORPUS = [
    ("academic/calendar.pdf", "academic", None, 0),
    ("major/CS101/lec1.pdf", "major", "CS101", 0),
    ("major/CS202/lec1.pdf", "major", "CS202", 0),
]


def server_for(session, courses):
    user = UserContext(user_id=1, courses=frozenset(courses))
    return build_server(user, session, lambda q: unit(0), k=5, min_score=0.0)


async def tool_names(server):
    async with connect(server) as client:
        return sorted(t.name for t in (await client.list_tools()).tools)


async def call(server, name, arguments):
    async with connect(server) as client:
        return parse_hits(await client.call_tool(name, arguments))


async def test_no_enrollment_sees_only_academic(session):
    assert await tool_names(server_for(session, [])) == [TOOL_ACADEMIC]


async def test_enrolled_student_sees_both_tools(session):
    assert await tool_names(server_for(session, ["CS101"])) == [TOOL_ACADEMIC, TOOL_MAJOR]


async def test_search_major_returns_only_enrolled_course(session):
    seed_chunks(session, CORPUS)
    hits = await call(server_for(session, ["CS101"]), TOOL_MAJOR, {"query": "스택"})
    assert [h.source for h in hits] == ["major/CS101/lec1.pdf"]


async def test_course_code_argument_cannot_widen(session):
    seed_chunks(session, CORPUS)
    assert await call(server_for(session, ["CS101"]), TOOL_MAJOR, {"query": "스택", "course_code": "CS202"}) == []


async def test_course_code_argument_narrows_case_insensitively(session):
    seed_chunks(session, CORPUS)
    hits = await call(server_for(session, ["CS101", "CS202"]), TOOL_MAJOR, {"query": "스택", "course_code": "cs101"})
    assert [h.source for h in hits] == ["major/CS101/lec1.pdf"]


async def test_hidden_tool_call_is_rejected(session):
    seed_chunks(session, CORPUS)
    with pytest.raises(ToolError):
        await call(server_for(session, []), TOOL_MAJOR, {"query": "스택"})


async def test_academic_search_is_open(session):
    seed_chunks(session, CORPUS)
    hits = await call(server_for(session, []), TOOL_ACADEMIC, {"query": "수강신청"})
    assert [h.source for h in hits] == ["academic/calendar.pdf"]


async def test_empty_query_is_rejected(session):
    with pytest.raises(ToolError):
        await call(server_for(session, []), TOOL_ACADEMIC, {"query": "  "})
```

- [ ] **Step 3: RED 확인** — Run: `make test` / Expected: FAIL `ModuleNotFoundError: No module named 'app.mcp.connection'`

- [ ] **Step 4: 구현**

`backend/app/mcp/server.py`:

```python
"""권한 겹 1 — 요청마다 사용자 컨텍스트를 품은 MCP 서버를 만든다. 설계 §4, 결정 2.

사용자 역할·수강 과목은 UserContext로만 들어온다. LLM이 만드는 도구 인자로는 받지 않는다.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass

from mcp import types
from mcp.server.lowlevel import Server
from sqlalchemy.orm import Session

from app.db.search import search_chunks

TOOL_ACADEMIC = "search_academic"
TOOL_MAJOR = "search_major"

_QUERY = {"type": "string", "description": "검색할 질문 또는 핵심 키워드"}
ACADEMIC_SCHEMA = {"type": "object", "properties": {"query": _QUERY}, "required": ["query"]}
MAJOR_SCHEMA = {
    "type": "object",
    "properties": {
        "query": _QUERY,
        "course_code": {"type": "string", "description": "특정 과목으로 좁힐 때 과목 코드 (예: CS101)"},
    },
    "required": ["query"],
}


@dataclass(frozen=True)
class UserContext:
    user_id: int
    courses: frozenset[str]


def visible_tools(user: UserContext) -> list[types.Tool]:
    tools = [
        types.Tool(
            name=TOOL_ACADEMIC,
            description="학사 규정·학사일정·학과 공지를 검색한다. 수강신청, 성적, 졸업, 장학, 휴학, 일정 질문에 사용한다.",
            inputSchema=ACADEMIC_SCHEMA,
        )
    ]
    if user.courses:
        tools.append(
            types.Tool(
                name=TOOL_MAJOR,
                description="사용자가 수강 중인 전공 과목의 강의자료를 검색한다. 과목 개념, 예제, 과제, 시험 범위 질문에 사용한다.",
                inputSchema=MAJOR_SCHEMA,
            )
        )
    return tools


def _error(message: str) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=message)], isError=True)


def build_server(
    user: UserContext,
    session: Session,
    embed_query: Callable[[str], Sequence[float]],
    *,
    k: int,
    min_score: float,
) -> Server:
    async def list_tools(ctx, params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=visible_tools(user))

    async def call_tool(ctx, params) -> types.CallToolResult:
        args = params.arguments or {}
        query = str(args.get("query", "")).strip()
        if params.name == TOOL_ACADEMIC:
            scope, allowed = "academic", frozenset()
        elif params.name == TOOL_MAJOR and user.courses:
            scope = "major"
            requested = args.get("course_code")
            # 인자는 좁히기만 한다: 수강 과목과의 교집합
            allowed = user.courses & {str(requested).upper()} if requested else user.courses
        else:
            return _error(f"사용할 수 없는 도구입니다: {params.name}")
        if not query:
            return _error("query가 비어 있습니다")
        hits = search_chunks(session, embed_query(query), scope=scope, allowed_courses=allowed, k=k, min_score=min_score)
        payload = json.dumps([asdict(h) for h in hits], ensure_ascii=False)
        return types.CallToolResult(content=[types.TextContent(type="text", text=payload)])

    return Server("dept-rag", on_list_tools=list_tools, on_call_tool=call_tool)
```

`backend/app/mcp/connection.py`:

```python
"""같은 프로세스 메모리 전송으로 MCP 서버에 붙는 클라이언트 (스파이크 S1에서 확인한 형태)."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio
from mcp import ClientSession, types
from mcp.server.lowlevel import Server
from mcp.shared.memory import create_client_server_memory_streams

from app.db.search import ChunkHit


class ToolError(RuntimeError):
    """MCP 도구가 isError 결과를 돌려줌."""


@asynccontextmanager
async def connect(server: Server) -> AsyncIterator[ClientSession]:
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        async with anyio.create_task_group() as tg:
            tg.start_soon(server.run, server_streams[0], server_streams[1], server.create_initialization_options())
            async with ClientSession(*client_streams) as client:
                await client.initialize()
                yield client
            tg.cancel_scope.cancel()


def parse_hits(result: types.CallToolResult) -> list[ChunkHit]:
    text = "".join(block.text for block in result.content if block.type == "text")
    if result.is_error:
        raise ToolError(text)
    return [ChunkHit(**item) for item in json.loads(text)]
```

- [ ] **Step 5: GREEN 확인** — Run: `make test` / Expected: PASS. 핸들러 시그니처·필드명이 SDK와 다르면 S1 스파이크 결과(M1 계획 "스파이크 결과" S1 행)를 따르고 보고서에 적는다.
- [ ] **Step 6: `make check` 후 커밋**

```bash
git add backend/app/mcp/ backend/tests/conftest.py backend/tests/fakes.py backend/tests/db/test_mcp_server.py
git commit -m "feat(mcp): 사용자 컨텍스트별 검색 도구 2종 (권한 겹 1)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 2: 답변 생성과 출처 검증

**Files:**
- Create: `backend/app/core/prompts/answer.md`, `backend/app/core/answer.py`, `backend/tests/test_answer.py`
- Modify: `backend/app/core/config.py` (설정 6개), `backend/tests/fakes.py` (`make_hit`, `FakeLLM` 추가), `.env.example` (`ANTHROPIC_API_KEY`는 이미 있음 — 변경 없음 확인)

**Interfaces:**
- Consumes: `ChunkHit`, `Settings`
- Produces:

```python
@dataclass(frozen=True)
class Source: file: str; page: int; section: str | None
@dataclass(frozen=True)
class Answer: text: str; sources: list[Source]; citation_ok: bool; notices: list[str] = []; retrieved: list[ChunkHit] = []
NO_EVIDENCE: str; REFUSED: str; FALLBACK_BETA = "server-side-fallback-2026-07-01"
def system_prompt() -> str
def prompt_hash() -> str            # sha256 앞 12자
def render_context(question: str, hits: Sequence[ChunkHit]) -> str
def verify_citations(raw: str, hits: Sequence[ChunkHit]) -> Answer
def generate_answer(llm: Any, question: str, hits: Sequence[ChunkHit], *, model: str, effort: str, max_tokens: int) -> Answer
def make_llm(settings: Settings) -> anthropic.Anthropic
# Settings 추가: anthropic_api_key="", generation_model="claude-sonnet-5-5", generation_effort="medium",
#               generation_max_tokens=4096, search_k=5, search_min_score=0.0
# tests/fakes.py
def make_hit(chunk_id: int, source: str = "academic/a.pdf", page: int = 1, section: str | None = None, score: float = 0.9) -> ChunkHit
class FakeLLM:  # .calls: list[dict]; FakeLLM(text="", stop_reason="end_turn"); .beta.messages.create(**kw)
```

- [ ] **Step 1: 테스트 헬퍼 추가** — `backend/tests/fakes.py` 상단 import에 `from types import SimpleNamespace`, `from app.db.search import ChunkHit`를 추가하고(ruff `I` 순서 유지) 끝에:

```python
def make_hit(chunk_id: int, source: str = "academic/a.pdf", page: int = 1,
             section: str | None = None, score: float = 0.9) -> ChunkHit:
    scope = "major" if source.startswith("major/") else "academic"
    course = source.split("/")[1] if scope == "major" else None
    return ChunkHit(chunk_id=chunk_id, text=f"조각 {chunk_id} 내용", source=source, page=page,
                    section=section, scope=scope, course_code=course, score=score)


class FakeLLM:
    """anthropic 클라이언트 대역. beta.messages.create 호출 인자를 기록하고 정해진 답을 돌려준다."""

    def __init__(self, text: str = "", stop_reason: str = "end_turn"):
        self.calls: list[dict] = []
        self.text = text
        self.stop_reason = stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        content = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=self.text)]
        return SimpleNamespace(stop_reason=self.stop_reason, content=content if self.stop_reason != "refusal" else [])
```

- [ ] **Step 2: 실패하는 테스트 작성** — `backend/tests/test_answer.py`:

```python
from app.core.answer import (
    FALLBACK_BETA, NO_EVIDENCE, REFUSED, Source, generate_answer, prompt_hash, system_prompt,
)
from tests.fakes import FakeLLM, make_hit

OPTS = {"model": "claude-sonnet-5-5", "effort": "medium", "max_tokens": 4096}


def test_no_hits_returns_no_evidence_without_calling_llm():
    llm = FakeLLM("무시됨")
    answer = generate_answer(llm, "질문", [], **OPTS)
    assert answer.text == NO_EVIDENCE and answer.sources == [] and llm.calls == []
    assert answer.notices == ["no_evidence"]


def test_citations_are_renumbered_and_sources_built_from_metadata():
    hits = [make_hit(12, "academic/학사일정.pdf", 2, "제3조(기간)"), make_hit(7, "academic/성적.pdf", 5)]
    llm = FakeLLM("정정 기간은 9월 8일부터다[C12]. 성적은 12월에 나온다[C7][C12].")
    answer = generate_answer(llm, "정정 기간?", hits, **OPTS)
    assert answer.text == "정정 기간은 9월 8일부터다[1]. 성적은 12월에 나온다[2][1]."
    assert answer.sources == [Source("academic/학사일정.pdf", 2, "제3조(기간)"), Source("academic/성적.pdf", 5, None)]
    assert answer.citation_ok is True
    assert [h.chunk_id for h in answer.retrieved] == [12, 7]


def test_unretrieved_citation_is_dropped():
    answer = generate_answer(FakeLLM("지어낸 규정이다[C99]."), "q", [make_hit(12)], **OPTS)
    assert answer.text == "지어낸 규정이다."
    assert answer.sources == []
    assert answer.citation_ok is False and answer.notices == ["invalid_citation"]


def test_refusal_does_not_read_content():
    answer = generate_answer(FakeLLM(stop_reason="refusal"), "q", [make_hit(1)], **OPTS)
    assert answer.text == REFUSED and answer.sources == [] and answer.notices == ["refused"]


def test_request_shape():
    llm = FakeLLM("답[C3]")
    generate_answer(llm, "휴학 신청은?", [make_hit(3, section="제9조(휴학)")], **OPTS)
    kw = llm.calls[0]
    assert kw["model"] == "claude-sonnet-5-5" and kw["max_tokens"] == 4096
    assert kw["betas"] == [FALLBACK_BETA] and kw["fallbacks"] == "default"
    assert kw["output_config"] == {"effort": "medium"}
    assert not {"temperature", "top_p", "top_k"} & set(kw)
    assert kw["system"] == system_prompt()
    user_text = kw["messages"][0]["content"]
    assert kw["messages"][0]["role"] == "user"
    assert "[C3]" in user_text and "제9조(휴학)" in user_text and "휴학 신청은?" in user_text


def test_prompt_hash_is_stable_short_hex():
    assert prompt_hash() == prompt_hash() and len(prompt_hash()) == 12
```

- [ ] **Step 3: RED 확인** — Run: `make test` / Expected: FAIL `ModuleNotFoundError: No module named 'app.core.answer'`

- [ ] **Step 4: 구현**

`backend/app/core/config.py`의 `Settings`에 필드 추가(`data_dir` 아래):

```python
    anthropic_api_key: str = ""
    generation_model: str = "claude-sonnet-5-5"
    generation_effort: str = "medium"
    generation_max_tokens: int = 4096
    search_k: int = 5
    search_min_score: float = 0.0
```

`backend/app/core/prompts/answer.md`:

```markdown
너는 학과 지식 질의응답 도우미다. 학생 질문에 `<자료>` 안의 조각만 근거로 한국어로 답한다.

규칙:
1. `<자료>`에 없는 내용은 쓰지 않는다. 일반 상식이나 추측으로 채우지 않는다.
2. 사실을 담은 문장마다 끝에 근거 조각 ID를 `[C12]` 형식으로 붙인다. 여러 조각이면 `[C12][C7]`.
3. 조각 ID는 `<자료>`에 나온 것만 쓴다.
4. 자료로 답할 수 없으면 "제공된 자료에서 답을 찾을 수 없습니다."라고만 쓰고 ID를 붙이지 않는다.
5. 날짜·기간·학점·조항 번호는 자료에 적힌 그대로 옮긴다.
6. 3~6문장으로 간결하게 답한다.
```

`backend/app/core/answer.py`:

```python
"""답변 생성과 출처 검증 — 설계 결정 4.

출처 문자열은 LLM이 쓴 텍스트가 아니라 조각 메타데이터(ChunkHit)로 코드가 만든다.
"""

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic

from app.core.config import Settings
from app.db.search import ChunkHit

PROMPT_PATH = Path(__file__).parent / "prompts" / "answer.md"
CITATION_RE = re.compile(r"\[C(\d+)\]")
FALLBACK_BETA = "server-side-fallback-2026-07-01"
NO_EVIDENCE = "관련 자료를 찾지 못했습니다. 질문을 조금 더 구체적으로 해 주세요."
REFUSED = "이 질문에는 답변할 수 없습니다."


@dataclass(frozen=True)
class Source:
    file: str
    page: int
    section: str | None


@dataclass(frozen=True)
class Answer:
    text: str
    sources: list[Source]
    citation_ok: bool
    notices: list[str] = field(default_factory=list)
    retrieved: list[ChunkHit] = field(default_factory=list)


def system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def prompt_hash() -> str:
    return hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()[:12]


def make_llm(settings: Settings) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.anthropic_api_key or None)


def render_context(question: str, hits: Sequence[ChunkHit]) -> str:
    blocks = []
    for h in hits:
        where = f"{h.source} p.{h.page}" + (f" {h.section}" if h.section else "")
        blocks.append(f"[C{h.chunk_id}] ({where})\n{h.text}")
    return "<자료>\n" + "\n\n".join(blocks) + "\n</자료>\n\n질문: " + question


def verify_citations(raw: str, hits: Sequence[ChunkHit]) -> Answer:
    by_id = {h.chunk_id: h for h in hits}
    order: list[int] = []
    invalid = False
    for m in CITATION_RE.finditer(raw):
        cid = int(m.group(1))
        if cid not in by_id:
            invalid = True
        elif cid not in order:
            order.append(cid)
    number = {cid: i + 1 for i, cid in enumerate(order)}
    text = CITATION_RE.sub(lambda m: f"[{number[int(m.group(1))]}]" if int(m.group(1)) in number else "", raw)
    sources = [Source(by_id[c].source, by_id[c].page, by_id[c].section) for c in order]
    return Answer(
        text=text.strip(),
        sources=sources,
        citation_ok=not invalid,
        notices=["invalid_citation"] if invalid else [],
        retrieved=list(hits),
    )


def generate_answer(llm: Any, question: str, hits: Sequence[ChunkHit], *, model: str, effort: str,
                    max_tokens: int) -> Answer:
    if not hits:
        return Answer(text=NO_EVIDENCE, sources=[], citation_ok=True, notices=["no_evidence"])
    response = llm.beta.messages.create(
        model=model,
        max_tokens=max_tokens,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        output_config={"effort": effort},
        system=system_prompt(),
        messages=[{"role": "user", "content": render_context(question, hits)}],
    )
    if response.stop_reason == "refusal":
        return Answer(text=REFUSED, sources=[], citation_ok=True, notices=["refused"], retrieved=list(hits))
    raw = "".join(block.text for block in response.content if block.type == "text")
    return verify_citations(raw, hits)
```

- [ ] **Step 5: GREEN 확인** — Run: `make test` / Expected: PASS
- [ ] **Step 6: `make check` 후 커밋**

```bash
git add backend/app/core/answer.py backend/app/core/prompts/ backend/app/core/config.py backend/tests/test_answer.py backend/tests/fakes.py
git commit -m "feat(core): 답변 생성과 인용 ID 검증·출처 조립

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 3: 기준선 파이프라인 (라우터 없음)

**Files:**
- Create: `backend/app/core/pipeline.py`, `backend/tests/db/test_pipeline.py`

**Interfaces:**
- Consumes: `UserContext`, `build_server`, `connect`, `parse_hits` (Task 1), `generate_answer`, `Answer` (Task 2), `Settings`, `ChunkHit`, `seed_chunks`, `FakeLLM`, `make_hit`, `unit`
- Produces:

```python
@dataclass(frozen=True)
class PipelineDeps: session: Session; embed_query: Callable[[str], Sequence[float]]; llm: Any; settings: Settings
def merge_hits(hits: Sequence[ChunkHit], *, k: int) -> list[ChunkHit]
async def answer_question(question: str, user: UserContext, deps: PipelineDeps) -> Answer
```

- [ ] **Step 1: 실패하는 테스트 작성** — `backend/tests/db/test_pipeline.py`:

```python
import pytest

from app.core.answer import NO_EVIDENCE
from app.core.config import Settings
from app.core.pipeline import PipelineDeps, answer_question, merge_hits
from app.mcp.server import UserContext
from tests.fakes import FakeLLM, make_hit, seed_chunks, unit

CORPUS = [
    ("academic/calendar.pdf", "academic", None, 0),
    ("major/CS101/lec1.pdf", "major", "CS101", 0),
    ("major/CS202/lec1.pdf", "major", "CS202", 0),
]


def deps(session, llm, axis=0, min_score=0.5):
    settings = Settings(_env_file=None, search_k=5, search_min_score=min_score)
    return PipelineDeps(session=session, embed_query=lambda q: unit(axis), llm=llm, settings=settings)


def user(*courses):
    return UserContext(user_id=1, courses=frozenset(courses))


@pytest.mark.anyio
async def test_enrolled_student_gets_academic_and_own_course(session):
    seed_chunks(session, CORPUS)
    answer = await answer_question("스택이 뭐야?", user("CS101"), deps(session, FakeLLM("답")))
    assert sorted(h.source for h in answer.retrieved) == ["academic/calendar.pdf", "major/CS101/lec1.pdf"]


@pytest.mark.anyio
async def test_no_enrollment_never_retrieves_major(session):
    seed_chunks(session, CORPUS)
    answer = await answer_question("스택이 뭐야?", user(), deps(session, FakeLLM("답")))
    assert [h.source for h in answer.retrieved] == ["academic/calendar.pdf"]


@pytest.mark.anyio
async def test_no_hits_skips_llm(session):
    seed_chunks(session, CORPUS)
    llm = FakeLLM("무시됨")
    answer = await answer_question("관계없는 질문", user("CS101"), deps(session, llm, axis=5))
    assert answer.text == NO_EVIDENCE and llm.calls == []


@pytest.mark.anyio
async def test_prompt_contains_only_permitted_chunks(session):
    seed_chunks(session, CORPUS)
    llm = FakeLLM("답")
    await answer_question("스택?", user("CS101"), deps(session, llm))
    prompt = llm.calls[0]["messages"][0]["content"]
    assert "major/CS101/lec1.pdf" in prompt and "major/CS202" not in prompt


def test_merge_hits_dedupes_keeps_best_score_and_limits():
    hits = [make_hit(1, score=0.5), make_hit(2, score=0.9), make_hit(1, score=0.8), make_hit(3, score=0.7)]
    merged = merge_hits(hits, k=2)
    assert [(h.chunk_id, h.score) for h in merged] == [(2, 0.9), (1, 0.8)]
```

- [ ] **Step 2: RED 확인** — Run: `make test` / Expected: FAIL `ModuleNotFoundError: No module named 'app.core.pipeline'`

- [ ] **Step 3: 구현** — `backend/app/core/pipeline.py`:

```python
"""M2 기준선 워크플로우 (설계 §8): 라우터 없이, 권한 안에서 보이는 모든 검색 도구를 호출하고 답한다.

4주차에 분류 → 처리 표(plan) 단계가 이 함수 앞에 들어온다.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.answer import Answer, generate_answer
from app.core.config import Settings
from app.db.search import ChunkHit
from app.mcp.connection import connect, parse_hits
from app.mcp.server import UserContext, build_server


@dataclass(frozen=True)
class PipelineDeps:
    session: Session
    embed_query: Callable[[str], Sequence[float]]
    llm: Any
    settings: Settings


def merge_hits(hits: Sequence[ChunkHit], *, k: int) -> list[ChunkHit]:
    best: dict[int, ChunkHit] = {}
    for h in hits:
        if h.chunk_id not in best or h.score > best[h.chunk_id].score:
            best[h.chunk_id] = h
    return sorted(best.values(), key=lambda h: (-h.score, h.chunk_id))[:k]


async def answer_question(question: str, user: UserContext, deps: PipelineDeps) -> Answer:
    s = deps.settings
    server = build_server(user, deps.session, deps.embed_query, k=s.search_k, min_score=s.search_min_score)
    hits: list[ChunkHit] = []
    async with connect(server) as client:
        listed = await client.list_tools()
        for name in sorted(tool.name for tool in listed.tools):
            hits.extend(parse_hits(await client.call_tool(name, {"query": question})))
    return generate_answer(deps.llm, question, merge_hits(hits, k=s.search_k),
                           model=s.generation_model, effort=s.generation_effort,
                           max_tokens=s.generation_max_tokens)
```

- [ ] **Step 4: GREEN 확인** — Run: `make test` / Expected: PASS
- [ ] **Step 5: `make check` 후 커밋**

```bash
git add backend/app/core/pipeline.py backend/tests/db/test_pipeline.py
git commit -m "feat(core): 라우터 없는 기준선 파이프라인

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 4: 평가셋과 지표

**Files:**
- Create: `backend/evaluation/__init__.py`(빈 파일), `backend/evaluation/dataset.py`, `backend/evaluation/metrics.py`, `backend/tests/evaluation/__init__.py`(빈 파일), `backend/tests/evaluation/test_dataset.py`, `backend/tests/evaluation/test_metrics.py`, `backend/tests/evaluation/test_eval_set.py`
- Modify: `backend/requirements.txt` (`pyyaml==6.0.3` 추가 — 이미 설치된 버전 고정)

**Interfaces:**
- Consumes: `ChunkHit`, `Source`
- Produces:

```python
INTENTS = frozenset({"major", "academic", "both", "none"})
REPO_ROOT: Path; QUESTIONS: Path  # eval/questions.yaml; FROZEN: Path  # eval/FROZEN
@dataclass(frozen=True) class GoldSource: file: str; page: int
@dataclass(frozen=True) class EvalItem: id: str; question: str; intent: str; gold_sources: tuple[GoldSource, ...]; key_points: tuple[str, ...]
def load_items(path: Path) -> list[EvalItem]          # 검증 실패 시 ValueError
def sha256_of(path: Path) -> str
def check_frozen(questions: Path, frozen: Path) -> None  # FROZEN이 있고 해시가 다르면 ValueError
def freeze(questions: Path, frozen: Path) -> str        # python -m evaluation.dataset --freeze
# metrics.py
def recall_at_k(item: EvalItem, retrieved: Sequence[ChunkHit]) -> bool | None
def source_match(item: EvalItem, sources: Sequence[Source]) -> bool | None
def none_handled(item: EvalItem, sources: Sequence[Source]) -> bool | None
def rate(values: Iterable[bool | None]) -> float | None
```

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/evaluation/test_dataset.py`:

```python
import pytest

from evaluation.dataset import EvalItem, GoldSource, check_frozen, freeze, load_items

VALID = """
- id: A01
  question: 수강신청 정정 기간은?
  intent: academic
  gold_sources: [{file: academic/학사일정.pdf, page: 2}]
  key_points: [9월 8일~9월 12일]
- id: N01
  question: 오늘 점심 메뉴 추천해줘
  intent: none
  gold_sources: []
  key_points: []
"""


def write(tmp_path, text, name="q.yaml"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_load_valid_items(tmp_path):
    items = load_items(write(tmp_path, VALID))
    assert items[0] == EvalItem("A01", "수강신청 정정 기간은?", "academic",
                                (GoldSource("academic/학사일정.pdf", 2),), ("9월 8일~9월 12일",))
    assert items[1].intent == "none" and items[1].gold_sources == ()


@pytest.mark.parametrize("bad, message", [
    (VALID.replace("id: N01", "id: A01"), "중복"),
    (VALID.replace("intent: academic", "intent: other"), "intent"),
    (VALID.replace("gold_sources: [{file: academic/학사일정.pdf, page: 2}]", "gold_sources: []"), "gold_sources"),
    (VALID.replace("gold_sources: []\n  key_points: []", "gold_sources: [{file: a.pdf, page: 1}]\n  key_points: []"), "none"),
    (VALID.replace("page: 2", "page: 0"), "page"),
    (VALID.replace("key_points: [9월 8일~9월 12일]", "key_points: []"), "key_points"),
])
def test_invalid_items_rejected(tmp_path, bad, message):
    with pytest.raises(ValueError, match=message):
        load_items(write(tmp_path, bad))


def test_check_frozen_passes_when_unfrozen_or_matching(tmp_path):
    q = write(tmp_path, VALID)
    check_frozen(q, tmp_path / "FROZEN")  # FROZEN 없음 → 통과
    freeze(q, tmp_path / "FROZEN")
    check_frozen(q, tmp_path / "FROZEN")


def test_check_frozen_rejects_changed_file(tmp_path):
    q = write(tmp_path, VALID)
    freeze(q, tmp_path / "FROZEN")
    q.write_text(VALID.replace("정정 기간은?", "정정 기간이 언제야?"), encoding="utf-8")
    with pytest.raises(ValueError, match="동결"):
        check_frozen(q, tmp_path / "FROZEN")
```

`backend/tests/evaluation/test_metrics.py`:

```python
from app.core.answer import Source
from evaluation.dataset import EvalItem, GoldSource
from evaluation.metrics import none_handled, rate, recall_at_k, source_match
from tests.fakes import make_hit

ITEM = EvalItem("A01", "q", "academic", (GoldSource("academic/a.pdf", 2),), ("k",))
NONE_ITEM = EvalItem("N01", "q", "none", (), ())


def test_recall_at_k():
    assert recall_at_k(ITEM, [make_hit(1, "academic/b.pdf", 2), make_hit(2, "academic/a.pdf", 2)]) is True
    assert recall_at_k(ITEM, [make_hit(1, "academic/a.pdf", 3)]) is False
    assert recall_at_k(NONE_ITEM, []) is None


def test_source_match():
    assert source_match(ITEM, [Source("academic/a.pdf", 2, None)]) is True
    assert source_match(ITEM, []) is False
    assert source_match(NONE_ITEM, []) is None


def test_none_handled():
    assert none_handled(NONE_ITEM, []) is True
    assert none_handled(NONE_ITEM, [Source("academic/a.pdf", 1, None)]) is False
    assert none_handled(ITEM, []) is None


def test_rate_ignores_none():
    assert rate([True, False, None, True]) == 2 / 3
    assert rate([None]) is None
```

`backend/tests/evaluation/test_eval_set.py` (실제 평가셋 — 게이트 1):

```python
import pytest

from evaluation.dataset import FROZEN, QUESTIONS, check_frozen, load_items


@pytest.mark.skipif(not QUESTIONS.exists(), reason="eval/questions.yaml 작성 전")
def test_real_eval_set_is_valid_and_frozen():
    items = load_items(QUESTIONS)
    assert len(items) >= 1
    check_frozen(QUESTIONS, FROZEN)
```

- [ ] **Step 2: RED 확인** — Run: `make test` / Expected: FAIL `ModuleNotFoundError: No module named 'evaluation'`

- [ ] **Step 3: 구현**

`backend/requirements.txt`의 `pypdf==6.19.0` 아래에 `pyyaml==6.0.3` 추가.

`backend/evaluation/dataset.py`:

```python
"""평가셋 로드·검증·동결 — 설계 §6. SoT는 eval/questions.yaml."""

import argparse
import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

INTENTS = frozenset({"major", "academic", "both", "none"})
REPO_ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = REPO_ROOT / "eval" / "questions.yaml"
FROZEN = REPO_ROOT / "eval" / "FROZEN"


@dataclass(frozen=True)
class GoldSource:
    file: str
    page: int


@dataclass(frozen=True)
class EvalItem:
    id: str
    question: str
    intent: str
    gold_sources: tuple[GoldSource, ...]
    key_points: tuple[str, ...]


def _item(raw: dict, index: int) -> EvalItem:
    label = str(raw.get("id") or f"#{index}")
    question = str(raw.get("question") or "").strip()
    intent = raw.get("intent")
    if not question:
        raise ValueError(f"{label}: question이 비어 있음")
    if intent not in INTENTS:
        raise ValueError(f"{label}: intent는 {sorted(INTENTS)} 중 하나")
    gold = []
    for g in raw.get("gold_sources") or []:
        page = g.get("page")
        if not isinstance(page, int) or page < 1:
            raise ValueError(f"{label}: gold_sources의 page는 1 이상의 정수")
        gold.append(GoldSource(str(g["file"]), page))
    key_points = tuple(str(k) for k in raw.get("key_points") or [])
    if intent == "none" and gold:
        raise ValueError(f"{label}: intent none에는 gold_sources를 두지 않음")
    if intent != "none" and not gold:
        raise ValueError(f"{label}: gold_sources가 필요함")
    if intent != "none" and not key_points:
        raise ValueError(f"{label}: key_points가 필요함")
    return EvalItem(label, question, intent, tuple(gold), key_points)


def load_items(path: Path) -> list[EvalItem]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    items = [_item(r, i) for i, r in enumerate(raw)]
    ids = [it.id for it in items]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValueError(f"id 중복: {dupes}")
    return items


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_frozen(questions: Path, frozen: Path) -> None:
    if frozen.exists() and frozen.read_text(encoding="utf-8").strip() != sha256_of(questions):
        raise ValueError("평가셋이 동결 이후 변경됨 — 비교표가 성립하지 않음 (eval/README.md 참고)")


def freeze(questions: Path, frozen: Path) -> str:
    digest = sha256_of(questions)
    frozen.write_text(digest + "\n", encoding="utf-8")
    return digest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="python -m evaluation.dataset")
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    items = load_items(QUESTIONS)
    if args.freeze:
        print(f"동결: {len(items)}문항, sha256 {freeze(QUESTIONS, FROZEN)}")
    else:
        check_frozen(QUESTIONS, FROZEN)
        print(f"검증 통과: {len(items)}문항")
```

`backend/evaluation/metrics.py`:

```python
"""자동 지표 3종 + none 처리. 사람 채점(답변 정확도)은 report.py가 grading CSV에서 읽는다."""

from collections.abc import Iterable, Sequence

from app.core.answer import Source
from app.db.search import ChunkHit
from evaluation.dataset import EvalItem


def _gold(item: EvalItem) -> set[tuple[str, int]]:
    return {(g.file, g.page) for g in item.gold_sources}


def recall_at_k(item: EvalItem, retrieved: Sequence[ChunkHit]) -> bool | None:
    if item.intent == "none":
        return None
    return any((h.source, h.page) in _gold(item) for h in retrieved)


def source_match(item: EvalItem, sources: Sequence[Source]) -> bool | None:
    if item.intent == "none":
        return None
    return any((s.file, s.page) in _gold(item) for s in sources)


def none_handled(item: EvalItem, sources: Sequence[Source]) -> bool | None:
    if item.intent != "none":
        return None
    return not sources


def rate(values: Iterable[bool | None]) -> float | None:
    known = [v for v in values if v is not None]
    return sum(known) / len(known) if known else None
```

- [ ] **Step 4: GREEN 확인** — Run: `make test` / Expected: PASS (`test_real_eval_set_is_valid_and_frozen`은 skip 1)
- [ ] **Step 5: `make check` 후 커밋**

```bash
git add backend/requirements.txt backend/evaluation/ backend/tests/evaluation/
git commit -m "feat(eval): 평가셋 검증·동결 검사와 자동 지표

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 5: 평가 실행과 비교표

**Files:**
- Create: `backend/evaluation/run.py`, `backend/evaluation/report.py`, `backend/tests/evaluation/test_run.py`, `backend/tests/evaluation/test_report.py`, `backend/tests/structural/test_public_repo_guard.py`
- Modify: `Makefile` (`eval`, `eval-freeze`, `eval-report`), `.gitignore` (`/eval/runs/`, `/eval/grading/`), `docs/generated/README.md` (행 추가)

**Interfaces:**
- Consumes: `EvalItem`, `load_items`, `check_frozen`, `QUESTIONS`, `FROZEN`, `REPO_ROOT` (Task 4), metrics (Task 4), `Answer`, `Source`, `prompt_hash`, `make_llm` (Task 2), `answer_question`, `PipelineDeps` (Task 3), `UserContext`, `OpenAIEmbedder`, `make_engine`, `get_settings`, `Document`
- Produces:

```python
def evaluate_item(item: EvalItem, answer: Answer, latency_ms: int) -> dict
async def run_items(items: Sequence[EvalItem], answer_fn: Callable[[str], Awaitable[Answer]], clock: Callable[[], float] = time.perf_counter) -> list[dict]
def write_run(records: list[dict], meta: dict, out_dir: Path, name: str) -> tuple[Path, Path]   # (runs/<name>.jsonl, grading/<name>.csv); meta는 runs/<name>.meta.json
# report.py
def summarize(meta: dict, records: list[dict], grading: dict[str, bool | None]) -> dict
def load_grading(path: Path) -> dict[str, bool | None]
def render(rows: list[dict]) -> str
def build_report(out_dir: Path) -> str
```

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/evaluation/test_run.py`:

```python
import csv
import json

import pytest

from app.core.answer import Answer, Source
from evaluation.dataset import EvalItem, GoldSource
from evaluation.run import evaluate_item, run_items, write_run
from tests.fakes import make_hit

ITEM = EvalItem("A01", "정정 기간?", "academic", (GoldSource("academic/a.pdf", 2),), ("9월 8일",))
ANSWER = Answer(text="9월 8일부터[1]", sources=[Source("academic/a.pdf", 2, None)], citation_ok=True,
                retrieved=[make_hit(1, "academic/a.pdf", 2)])


def test_evaluate_item_record():
    rec = evaluate_item(ITEM, ANSWER, 1234)
    assert rec["id"] == "A01" and rec["intent"] == "academic" and rec["latency_ms"] == 1234
    assert rec["recall_at_k"] is True and rec["source_match"] is True and rec["none_handled"] is None
    assert rec["sources"] == [{"file": "academic/a.pdf", "page": 2, "section": None}]
    assert rec["retrieved"] == [{"source": "academic/a.pdf", "page": 2, "score": 0.9}]


@pytest.mark.anyio
async def test_run_items_measures_latency_in_order():
    ticks = iter([0.0, 0.5, 1.0, 3.0])

    async def answer_fn(question):
        return ANSWER

    records = await run_items([ITEM, ITEM], answer_fn, clock=lambda: next(ticks))
    assert [r["latency_ms"] for r in records] == [500, 2000]


def test_write_run_creates_jsonl_meta_and_grading_template(tmp_path):
    rec = evaluate_item(ITEM, ANSWER, 10)
    run_path, grading_path = write_run([rec], {"label": "baseline"}, tmp_path, "2026-10-01-baseline-abc1234")
    assert json.loads(run_path.read_text(encoding="utf-8").splitlines()[0])["id"] == "A01"
    assert json.loads((tmp_path / "runs" / "2026-10-01-baseline-abc1234.meta.json").read_text())["label"] == "baseline"
    rows = list(csv.DictReader(grading_path.open(encoding="utf-8-sig")))
    assert rows[0]["id"] == "A01" and rows[0]["key_points"] == "9월 8일"
    assert rows[0]["key_points_ok"] == "" and rows[0]["no_hallucination"] == ""
```

`backend/tests/evaluation/test_report.py`:

```python
import csv
import json

from evaluation.report import build_report, load_grading, summarize


def make_run(out, name, records, meta, grading_rows=None):
    (out / "runs").mkdir(parents=True, exist_ok=True)
    (out / "runs" / f"{name}.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    (out / "runs" / f"{name}.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    if grading_rows is not None:
        (out / "grading").mkdir(parents=True, exist_ok=True)
        with (out / "grading" / f"{name}.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id", "key_points_ok", "no_hallucination"])
            w.writeheader()
            w.writerows(grading_rows)


RECORDS = [
    {"id": "A01", "recall_at_k": True, "source_match": True, "none_handled": None, "citation_ok": True, "latency_ms": 100},
    {"id": "A02", "recall_at_k": False, "source_match": False, "none_handled": None, "citation_ok": False, "latency_ms": 300},
    {"id": "N01", "recall_at_k": None, "source_match": None, "none_handled": True, "citation_ok": True, "latency_ms": 200},
]


def test_load_grading_requires_both_marks(tmp_path):
    make_run(tmp_path, "r", RECORDS, {}, [
        {"id": "A01", "key_points_ok": "O", "no_hallucination": "O"},
        {"id": "A02", "key_points_ok": "O", "no_hallucination": "X"},
        {"id": "N01", "key_points_ok": "", "no_hallucination": ""},
    ])
    assert load_grading(tmp_path / "grading" / "r.csv") == {"A01": True, "A02": False, "N01": None}


def test_summarize_rates():
    s = summarize({"label": "baseline"}, RECORDS, {"A01": True, "A02": False, "N01": None})
    assert s["n"] == 3 and s["recall_at_k"] == 0.5 and s["source_match"] == 0.5
    assert s["none_handled"] == 1.0 and s["answer_accuracy"] == 0.5 and s["graded"] == 2
    assert s["latency_p50_ms"] == 200


def test_build_report_is_deterministic_and_marks_ungraded(tmp_path):
    make_run(tmp_path, "2026-10-01-baseline-abc", RECORDS, {"label": "baseline", "prompt_hash": "p1"})
    first = build_report(tmp_path)
    assert first == build_report(tmp_path)
    assert first.startswith("<!-- DO NOT EDIT")
    assert "2026-10-01-baseline-abc" in first and "50.0%" in first and "—" in first
```

`backend/tests/structural/test_public_repo_guard.py`:

```python
"""레포가 PUBLIC — 강의자료 원문이 섞이는 평가 산출물과 원본 PDF가 git에 올라가지 않아야 한다."""

from pathlib import Path

GITIGNORE = Path(__file__).resolve().parents[3] / ".gitignore"


def test_sensitive_outputs_are_gitignored():
    lines = {line.strip() for line in GITIGNORE.read_text(encoding="utf-8").splitlines()}
    assert {"/data/", "/eval/runs/", "/eval/grading/"} <= lines
```

- [ ] **Step 2: RED 확인** — Run: `make test` / Expected: FAIL `ModuleNotFoundError: No module named 'evaluation.run'` (+ gitignore 가드 실패)

- [ ] **Step 3: 구현**

`.gitignore` 끝에:

```
# 평가 산출물 — 강의자료 원문 포함 (레포 PUBLIC). 비교표는 docs/generated/에 집계만 커밋
/eval/runs/
/eval/grading/
```

`backend/evaluation/run.py`:

```python
"""평가 실행 — `make eval LABEL=baseline`. 설계 §6.

결과: eval/runs/<날짜>-<label>-<커밋>.jsonl (+ .meta.json), 사람 채점 양식 eval/grading/<같은 이름>.csv.
둘 다 gitignore (강의자료 원문 포함).
"""

import argparse
import csv
import json
import subprocess
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict
from datetime import date
from pathlib import Path

import anyio
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.answer import Answer, make_llm, prompt_hash
from app.core.config import get_settings
from app.core.embeddings import OpenAIEmbedder
from app.core.pipeline import PipelineDeps, answer_question
from app.db.models import Document
from app.db.session import make_engine
from app.mcp.server import UserContext
from evaluation.dataset import FROZEN, QUESTIONS, REPO_ROOT, EvalItem, check_frozen, load_items
from evaluation.metrics import none_handled, rate, recall_at_k, source_match

GRADING_FIELDS = ["id", "question", "answer", "key_points", "key_points_ok", "no_hallucination", "note"]


def evaluate_item(item: EvalItem, answer: Answer, latency_ms: int) -> dict:
    return {
        "id": item.id,
        "intent": item.intent,
        "question": item.question,
        "answer": answer.text,
        "sources": [asdict(s) for s in answer.sources],
        "retrieved": [{"source": h.source, "page": h.page, "score": round(h.score, 4)} for h in answer.retrieved],
        "notices": list(answer.notices),
        "citation_ok": answer.citation_ok,
        "latency_ms": latency_ms,
        "recall_at_k": recall_at_k(item, answer.retrieved),
        "source_match": source_match(item, answer.sources),
        "none_handled": none_handled(item, answer.sources),
        "key_points": list(item.key_points),
    }


async def run_items(items: Sequence[EvalItem], answer_fn: Callable[[str], Awaitable[Answer]],
                    clock: Callable[[], float] = time.perf_counter) -> list[dict]:
    records = []
    for item in items:
        started = clock()
        answer = await answer_fn(item.question)
        records.append(evaluate_item(item, answer, round((clock() - started) * 1000)))
    return records


def write_run(records: list[dict], meta: dict, out_dir: Path, name: str) -> tuple[Path, Path]:
    runs, grading = out_dir / "runs", out_dir / "grading"
    runs.mkdir(parents=True, exist_ok=True)
    grading.mkdir(parents=True, exist_ok=True)
    run_path = runs / f"{name}.jsonl"
    run_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    (runs / f"{name}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    grading_path = grading / f"{name}.csv"
    with grading_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=GRADING_FIELDS)
        writer.writeheader()
        for r in records:
            writer.writerow({"id": r["id"], "question": r["question"], "answer": r["answer"],
                             "key_points": " / ".join(r["key_points"]), "key_points_ok": "",
                             "no_hallucination": "", "note": ""})
    return run_path, grading_path


def _commit() -> str:
    out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True)
    return out.stdout.strip() or "nogit"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m evaluation.run")
    parser.add_argument("--label", required=True)
    args = parser.parse_args(argv)
    items = load_items(QUESTIONS)
    check_frozen(QUESTIONS, FROZEN)
    settings = get_settings()
    embedder = OpenAIEmbedder.from_settings(settings)
    llm = make_llm(settings)
    name = f"{date.today().isoformat()}-{args.label}-{_commit()}"
    with Session(make_engine()) as session:
        # 평가 전용 계정: 모든 과목 수강 (설계 §5 — 의도 측정이 권한에 섞이지 않게)
        courses = frozenset(c for c in session.scalars(select(Document.course_code).distinct()) if c)
        deps = PipelineDeps(session=session, embed_query=lambda q: embedder.embed([q])[0], llm=llm, settings=settings)
        user = UserContext(user_id=0, courses=courses)
        records = anyio.run(run_items, items, lambda q: answer_question(q, user, deps))
    meta = {"label": args.label, "commit": _commit(), "prompt_hash": prompt_hash(),
            "model": settings.generation_model, "effort": settings.generation_effort,
            "k": settings.search_k, "min_score": settings.search_min_score, "n": len(records)}
    run_path, grading_path = write_run(records, meta, REPO_ROOT / "eval", name)
    print(f"{name}: recall@k {rate(r['recall_at_k'] for r in records)}, "
          f"출처 일치 {rate(r['source_match'] for r in records)}, none {rate(r['none_handled'] for r in records)}")
    print(f"채점 양식: {grading_path}  →  채점 후 make eval-report")


if __name__ == "__main__":
    main()
```

`backend/evaluation/report.py`:

```python
"""평가 비교표 — `make eval-report` → docs/generated/eval-comparison.md (결정론적, 집계만)."""

import csv
import json
import statistics
from pathlib import Path

from evaluation.dataset import REPO_ROOT
from evaluation.metrics import rate

OUTPUT = REPO_ROOT / "docs" / "generated" / "eval-comparison.md"
HEADER = "<!-- DO NOT EDIT — generated by `make eval-report` from eval/runs + eval/grading -->"


def load_grading(path: Path) -> dict[str, bool | None]:
    result: dict[str, bool | None] = {}
    with path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            marks = (row.get("key_points_ok", "").strip().upper(), row.get("no_hallucination", "").strip().upper())
            result[row["id"]] = None if "" in marks else marks == ("O", "O")
    return result


def summarize(meta: dict, records: list[dict], grading: dict[str, bool | None]) -> dict:
    graded = [grading.get(r["id"]) for r in records]
    return {
        "label": meta.get("label", ""),
        "prompt_hash": meta.get("prompt_hash", ""),
        "n": len(records),
        "recall_at_k": rate(r["recall_at_k"] for r in records),
        "source_match": rate(r["source_match"] for r in records),
        "none_handled": rate(r["none_handled"] for r in records),
        "citation_ok": rate(r["citation_ok"] for r in records),
        "answer_accuracy": rate(graded),
        "graded": sum(g is not None for g in graded),
        "latency_p50_ms": round(statistics.median(r["latency_ms"] for r in records)) if records else None,
    }


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def render(rows: list[dict]) -> str:
    lines = [HEADER, "", "# 평가 비교표", "",
             "| 실행 | 라벨 | 프롬프트 | 문항 | 답변 정확도 (채점 수) | recall@k | 출처 일치 | none 처리 | 인용 정상 | 응답 p50 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['name']} | {r['label']} | {r['prompt_hash']} | {r['n']} | "
                     f"{_pct(r['answer_accuracy'])} ({r['graded']}) | {_pct(r['recall_at_k'])} | "
                     f"{_pct(r['source_match'])} | {_pct(r['none_handled'])} | {_pct(r['citation_ok'])} | "
                     f"{'—' if r['latency_p50_ms'] is None else str(r['latency_p50_ms']) + 'ms'} |")
    return "\n".join(lines) + "\n"


def build_report(out_dir: Path) -> str:
    rows = []
    for run_path in sorted((out_dir / "runs").glob("*.jsonl")):
        name = run_path.stem
        records = [json.loads(line) for line in run_path.read_text(encoding="utf-8").splitlines() if line]
        meta_path = run_path.with_name(f"{name}.meta.json")
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        grading_path = out_dir / "grading" / f"{name}.csv"
        grading = load_grading(grading_path) if grading_path.exists() else {}
        rows.append({"name": name, **summarize(meta, records, grading)})
    return render(rows)


if __name__ == "__main__":
    OUTPUT.write_text(build_report(REPO_ROOT / "eval"), encoding="utf-8")
    print(f"wrote {OUTPUT}")
```

`Makefile`: `.PHONY`에 `eval eval-freeze eval-report` 추가, 끝에:

```make
# 평가 (설계 §6) — 실제 API 호출·비용 발생. LABEL 예: baseline, router-v1
eval:
	PYTHONPATH=backend $(PY) -m evaluation.run --label $(LABEL)

eval-freeze:
	PYTHONPATH=backend $(PY) -m evaluation.dataset --freeze

eval-report:
	PYTHONPATH=backend $(PY) -m evaluation.report
```

`docs/generated/README.md` 표에 행 추가:

```markdown
| `eval-comparison.md` | `eval/runs/`, `eval/grading/` (로컬 전용) | `backend/evaluation/report.py` (`make eval-report`) |
```

- [ ] **Step 4: GREEN 확인** — Run: `make test` / Expected: PASS
- [ ] **Step 5: `make check` 후 커밋**

```bash
git add backend/evaluation/run.py backend/evaluation/report.py backend/tests/evaluation/test_run.py \
  backend/tests/evaluation/test_report.py backend/tests/structural/test_public_repo_guard.py \
  Makefile .gitignore docs/generated/README.md
git commit -m "feat(eval): 평가 실행·채점 양식·비교표 생성

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 6: 문서와 평가 가이드

**Files:**
- Create: `eval/README.md`, `eval/RUBRIC.md`
- Modify: `docs/sot.md`, `AGENTS.md`, `docs/design/2026-09-28-system-design.md`, `docs/exec-plans/done/2026-09-29-m1-data-permission.md`

- [ ] **Step 1: `eval/README.md`**

```markdown
# 평가셋 (설계 §6)

## 파일
| 파일 | 내용 | git |
|---|---|---|
| `questions.yaml` | 평가 문항 SoT (제출용 30 + 보조 6) | 커밋 |
| `FROZEN` | 동결 시점 `questions.yaml`의 sha256 | 커밋 |
| `RUBRIC.md` | 사람 채점 기준 | 커밋 |
| `runs/`, `grading/` | 실행 결과·채점표 (강의자료 원문 포함) | **gitignore** (레포 PUBLIC) |

## 문항 형식
```yaml
- id: A01                      # 전공 M##, 학사 A##, both B##, none N##
  question: 2학기 수강신청 정정 기간이 언제야?
  intent: academic             # major | academic | both | none
  gold_sources: [{file: academic/학사일정.pdf, page: 2}]   # data/ 기준 상대 경로, none이면 []
  key_points: [9월 8일~9월 12일]                          # 답에 꼭 들어가야 할 사실, none이면 []
```
- 문항은 **적재한 PDF를 보면서** 쓴다. `file`은 `data/` 아래 상대 경로와 정확히 같아야 한다.
- 강의자료 문장을 길게 베끼지 않는다(레포 PUBLIC). `key_points`는 짧은 사실만.

## 순서
1. 36문항 작성 → `make eval-freeze` (이후 수정하면 `make check` 실패)
2. `make eval LABEL=baseline` → `grading/<실행>.csv`에 `RUBRIC.md` 기준으로 O/X
3. `make eval-report` → `docs/generated/eval-comparison.md` 커밋
```

- [ ] **Step 2: `eval/RUBRIC.md`**

```markdown
# 채점 기준 (3주차 1차 측정 전 고정, 이후 변경 금지)

문항마다 두 칸에 `O` 또는 `X`. 둘 다 `O`여야 정답.

| 칸 | O | X |
|---|---|---|
| `key_points_ok` | `key_points`의 사실을 **모두** 담음 (표현이 달라도 뜻이 같으면 O) | 하나라도 빠지거나 틀림 |
| `no_hallucination` | 답의 모든 사실 주장이 인용한 출처에 있음 | 출처에 없는 사실·수치·조항이 하나라도 있음 |

- `intent: none` 문항: "자료에서 찾을 수 없다"류로 답했으면 두 칸 모두 O.
- 애매하면 X로 두고 `note`에 이유를 쓴다.
```

- [ ] **Step 3: `docs/sot.md` 행 추가** (표 끝에)

```markdown
| 평가셋 | `eval/questions.yaml` (+ `eval/FROZEN`) | 평가 실행 기록, 비교표 | `tests/evaluation/test_eval_set.py` (동결 검사, 게이트 1) |
| 채점 기준 | `eval/RUBRIC.md` | `eval/grading/*.csv` | - |
| 답변 생성 프롬프트 | `backend/app/core/prompts/answer.md` | 평가 실행 meta의 `prompt_hash` | 실행 기록 |
| 평가 비교표 | `eval/runs/`, `eval/grading/` (로컬) | `docs/generated/eval-comparison.md` | `make eval-report` 재생성 |
```

- [ ] **Step 4: `AGENTS.md` 명령 표에 행 추가**

```markdown
| 평가 | `make eval LABEL=baseline` → 채점 → `make eval-report` | 실제 API 비용 발생. 가이드 `eval/README.md` |
| 평가셋 동결 | `make eval-freeze` | 이후 `eval/questions.yaml` 수정 시 `make check` 실패 |
```

- [ ] **Step 5: 설계 문서 정정** — `docs/design/2026-09-28-system-design.md` §6의 `temperature 0`을 `effort 고정(설정값), 샘플링 파라미터 미사용 — Sonnet 5.5는 기본값 아닌 temperature에 400`으로 바꾸고, §5 첫 줄의 모델 설명 뒤에 `(생성 기본값 claude-sonnet-5-5 / effort medium, 거절 시 fallbacks "default")`를 덧붙인다.

- [ ] **Step 6: M1 계획 체크** — `docs/exec-plans/done/2026-09-29-m1-data-permission.md`의 `- [ ] CI에서 DB 테스트가 실제로 실행됨(건너뛰지 않음)`을 `- [x] … — PR #4 CI 73 passed, skip 0 (2026-09-29)`로 바꾼다.

- [ ] **Step 7: `make check` 후 커밋**

```bash
git add eval/README.md eval/RUBRIC.md docs/sot.md AGENTS.md docs/design/2026-09-28-system-design.md docs/exec-plans/done/2026-09-29-m1-data-permission.md
git commit -m "docs: 평가 가이드·채점 기준, SoT·설계 갱신

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## 튜터 작업 (구현 후, 사람)

1. `.env`: `DATABASE_URL` 포트 5433, `ANTHROPIC_API_KEY`·`OPENAI_API_KEY` 확인. Anthropic·OpenAI 콘솔 월 지출 한도 설정.
2. PDF를 `data/academic/`, `data/major/<과목코드>/`에 두고 `make db-up && make migrate && make ingest`.
3. `eval/questions.yaml` 36문항 작성 → `make check`(형식 검증) → `make eval-freeze` → 커밋.
4. `make eval LABEL=baseline` → `eval/grading/…csv` 채점 → `make eval-report` → 비교표 커밋.
5. 3주차 보고서: 비교표의 기준선 수치 인용.

## 결정 로그

- 2026-09-29: 계획 작성. 기준선 = 라우터 없이 권한 안의 모든 도구 호출(설계 §8).
- 2026-09-29: 생성 모델 `claude-sonnet-5-5`(설계 §5 "Sonnet 계열"), `temperature` 미사용 — Sonnet 5.5는 기본값 아닌 샘플링 값에 400. 재현성은 effort 고정 + 프롬프트 해시 기록으로 대신한다.
- 2026-09-29: 거절 대비 `fallbacks: "default"`(beta `server-side-fallback-2026-07-01`) 기본 적용.
- 2026-09-29: `app/mcp`는 `app/core`를 import하지 않도록 임베딩을 `embed_query` 호출 가능 객체로 주입.
- 2026-09-29: 레포 PUBLIC 확인 → 평가 산출물 gitignore + 구조 테스트로 강제.
- 2026-09-29: M2의 생성 호출은 동기 SDK를 async 파이프라인 안에서 부른다(단일 사용자 평가용). M3에서 API에 연결할 때 `AsyncAnthropic`으로 바꾼다.
