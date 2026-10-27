"""6주차 agent 모드 — 모델이 도구를 고르는 루프 (설계 §5 "에이전트 루프").

루프 4요소를 run_agent 한 함수에 순서대로 드러낸다:
  ① 권한 필터된 list_tools → 모델의 tools   ② tool_use → MCP call_tool
  ③ 결과 조각·ID 누적                        ④ 종료: 도구 없는 응답 또는 도구 호출 상한(강제 생성)
workflow는 코드가 도구를 고르고 agent는 모델이 고른다. 권한은 둘 다 코드(MCP 목록·SQL 조건)가 정한다 —
모델 입력에는 역할·수강 과목을 넣지 않는다.
"""

import hashlib
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import anyio
from mcp import ClientSession, types
from mcp.shared.exceptions import MCPError

from app.core.answer import (
    EMPTY,
    FALLBACK_BETA,
    REFUSED,
    Answer,
    generate_answer,
    render_chunks,
    verify_citations,
)
from app.core.config import Settings
from app.db.search import ChunkHit
from app.mcp.connection import ToolError, parse_hits

PROMPT_PATH = Path(__file__).parent / "prompts" / "agent.md"
NO_RESULTS = "검색 결과 없음"
TOOL_LIMIT_REACHED = "tool_limit_reached"
INVALID_TOOL_CALL = "invalid_tool_call"
INVALID_CALL_TEXT = "사용할 수 없는 도구이거나 query가 올바르지 않습니다"


def agent_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def agent_prompt_hash() -> str:
    """평가 meta에 남겨, 에이전트 프롬프트가 바뀐 실행끼리 비교하는 실수를 막는다."""
    return hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()[:12]


def to_model_tool(tool: types.Tool) -> dict:
    return {"name": tool.name, "description": tool.description or "", "input_schema": tool.input_schema}


def _sorted_hits(found: dict[int, ChunkHit]) -> list[ChunkHit]:
    return sorted(found.values(), key=lambda h: (-h.score, h.chunk_id))


def _is_valid_call(use: Any, visible: set[str]) -> bool:
    """모델이 보지 못한 도구·문자열이 아닌 query는 MCP까지 보내지 않는다. MCP도 같은 검사를 하지만(두 번째 방어선),
    거기서 거절되면 tool_error 공지로 섞여 모델의 실수가 장애처럼 집계된다."""
    query = use.input.get("query") if isinstance(use.input, dict) else None
    return use.name in visible and isinstance(query, str) and bool(query.strip())


def _final_answer(response: Any, hits: list[ChunkHit]) -> Answer:
    """도구 없는 응답을 답으로 바꾼다. 거절·빈 응답·잘림 처리는 generate_answer와 같은 규칙이다."""
    if response.stop_reason == "refusal":  # 거절 응답의 content는 읽지 않는다
        return Answer(text=REFUSED, sources=[], citation_ok=True, notices=["refused"], retrieved=hits)
    raw = "".join(b.text for b in response.content if b.type == "text")
    if not raw.strip():
        return Answer(text=EMPTY, sources=[], citation_ok=True, notices=["empty"], retrieved=hits)
    answer = verify_citations(raw, hits)
    if response.stop_reason == "max_tokens":
        answer = replace(answer, notices=answer.notices + ["truncated"])
    return answer


async def run_agent(question: str, client: ClientSession, llm: Any, settings: Settings, *, today: date,
                    check_upstream: Callable[[], None]) -> Answer:
    """check_upstream: 도구 호출마다 부른다. 도구 안에서 난 임베딩 공급사 장애를 원래 예외로 다시 던져야
    API가 503으로 바꾸고 한도를 되돌린다 — 안 부르면 장애가 "자료 없음" 답 + 한도 차감이 된다."""
    s = settings
    # ① 모델이 볼 도구 = MCP가 이 사용자에게 보여 준 도구 그대로. 여기서 목록을 손으로 만들면 권한 겹 ①을 우회한다
    listed = (await client.list_tools()).tools
    tools = [to_model_tool(t) for t in listed]
    visible = {t.name for t in listed}
    messages: list[dict] = [{"role": "user", "content": f"오늘 날짜: {today.isoformat()}\n\n질문: {question}"}]
    # ③ 누적: 최종 인용은 루프 전체 조각으로 검증한다. 마지막 호출 결과나 top-k만 남기면
    # 앞선 호출의 조각을 인용한 정상 문장이 invalid_citation이 된다
    found: dict[int, ChunkHit] = {}
    tools_called: list[str] = []
    notices: list[str] = []
    calls_used = 0  # 잘못된 호출도 센다 — 안 세면 모델이 같은 잘못된 호출을 끝없이 반복할 수 있다

    def finish(answer: Answer) -> Answer:
        return replace(answer, notices=notices + answer.notices, tools_called=tools_called)

    while True:
        response = await anyio.to_thread.run_sync(lambda: llm.beta.messages.create(
            model=s.generation_model, max_tokens=s.generation_max_tokens, betas=[FALLBACK_BETA], fallbacks="default",
            output_config={"effort": s.generation_effort}, system=agent_prompt(), tools=tools, messages=messages))
        uses = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not uses:  # ④-1 도구 없는 응답 = 최종 답
            return finish(_final_answer(response, _sorted_hits(found)))
        if calls_used >= s.agent_max_tool_calls:
            break
        # 다음 턴에 응답 content를 그대로 돌려준다 — thinking 블록을 빼거나 다시 만들면 API가 400을 낸다
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for use in uses:  # ② tool_use → MCP call_tool
            if calls_used >= s.agent_max_tool_calls:
                break
            calls_used += 1
            if not _is_valid_call(use, visible):
                if INVALID_TOOL_CALL not in notices:
                    notices.append(INVALID_TOOL_CALL)
                results.append({"type": "tool_result", "tool_use_id": use.id, "content": INVALID_CALL_TEXT,
                                "is_error": True})
                continue
            try:
                hits = parse_hits(await client.call_tool(use.name, use.input))
            except (ToolError, MCPError) as e:
                # MCP 2.2는 도구 안 예외를 isError가 아니라 MCPError로 던진다. 임베딩 장애면 여기서 원래 예외로 바뀐다
                check_upstream()
                notices.append(f"tool_error:{use.name}")  # workflow와 같은 코드 — 화면·평가가 한 규칙으로 센다
                results.append({"type": "tool_result", "tool_use_id": use.id, "content": str(e) or "도구 오류",
                                "is_error": True})
                continue
            check_upstream()
            tools_called.append(use.name)
            for h in hits:
                if h.chunk_id not in found or h.score > found[h.chunk_id].score:
                    found[h.chunk_id] = h
            results.append({"type": "tool_result", "tool_use_id": use.id, "content": render_chunks(hits) or NO_RESULTS})
        if len(results) < len(uses):  # 한 응답 안에서 상한에 닿음 — 남은 블록은 실행하지 않는다
            break
        messages.append({"role": "user", "content": results})

    # ④-2 상한 도달: 더 찾지 않고 누적 조각으로 강제 생성. workflow와 같은 생성·검증 코드를 지나야 7주차 비교가 공정하다
    forced = await anyio.to_thread.run_sync(lambda: generate_answer(
        llm, question, _sorted_hits(found), model=s.generation_model, effort=s.generation_effort,
        max_tokens=s.generation_max_tokens, today=today))
    notices.append(TOOL_LIMIT_REACHED)
    return finish(replace(forced, retrieved=_sorted_hits(found)))
