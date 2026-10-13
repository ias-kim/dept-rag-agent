"""질문 → 답변 워크플로우 (설계 §2·§5).

- baseline: 라우터 없이 권한 안에서 보이는 모든 검색 도구를 호출 (3주차 기준선)
- workflow: 분류(LLM) → 처리 표(코드) → 표가 고른 도구만 호출 (4주차)
두 모드가 같은 함수를 지나야 라우터 효과를 같은 조건에서 비교할 수 있다.
동기 Anthropic SDK 호출은 anyio.to_thread로 이벤트 루프 밖에서 부른다 — 루프 안에서 부르면 그동안 다른 요청이 멈춘다.
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


@dataclass(frozen=True)
class PipelineDeps:
    session: Session
    embed_query: Callable[[str], Sequence[float]]
    llm: Any
    settings: Settings
    today: Callable[[], date] = seoul_today  # 테스트는 고정 날짜를 넣는다


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
    planned_tools: tuple[str, ...] | None = None  # None = 보이는 도구 전부 (baseline)
    notices: list[str] = []

    if mode == "workflow":
        classification = await anyio.to_thread.run_sync(
            lambda: classify(deps.llm, question, model=s.classify_model, max_tokens=s.classify_max_tokens))
        intent, intent_valid = classification.intent, classification.valid
        route = plan(intent, user)
        planned_tools, notices = route.tools, list(route.notices)
        if not planned_tools:  # none 의도·미수강자의 major: 검색·생성 비용 없이 안내만
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
        # 처리 표가 골라도 MCP 목록(권한 겹 ①)에 없는 도구는 부르지 않는다 — 표와 권한이 어긋나도 권한이 이긴다
        tool_names = sorted(visible) if planned_tools is None else [n for n in planned_tools if n in visible]
        for name in tool_names:
            try:
                hits.extend(parse_hits(await client.call_tool(name, {"query": question})))
            except ToolError:
                notices.append(f"tool_error:{name}")  # 도구 하나의 실패가 답변 전체를 막지 않게 한다
    today = deps.today()
    answer = await anyio.to_thread.run_sync(
        lambda: generate_answer(deps.llm, question, merge_hits(hits, k=s.search_k), model=s.generation_model,
                                effort=s.generation_effort, max_tokens=s.generation_max_tokens, today=today))
    return replace(answer, notices=notices + answer.notices, intent=intent, intent_valid=intent_valid)
