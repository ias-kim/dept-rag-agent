"""6주차 agent 모드 — 모델이 도구를 고르는 루프 (설계 §5 "에이전트 루프").

루프 4요소를 run_agent 한 함수에 순서대로 드러낸다:
  ① 권한 필터된 list_tools → 모델의 tools   ② tool_use → MCP call_tool
  ③ 결과 조각·ID 누적                        ④ 종료: 도구 없는 응답
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

from app.core.answer import FALLBACK_BETA, Answer, render_chunks, verify_citations
from app.core.config import Settings
from app.db.search import ChunkHit
from app.mcp.connection import parse_hits

PROMPT_PATH = Path(__file__).parent / "prompts" / "agent.md"
NO_RESULTS = "검색 결과 없음"


def agent_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def agent_prompt_hash() -> str:
    """평가 meta에 남겨, 에이전트 프롬프트가 바뀐 실행끼리 비교하는 실수를 막는다."""
    return hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()[:12]


def to_model_tool(tool: types.Tool) -> dict:
    return {"name": tool.name, "description": tool.description or "", "input_schema": tool.input_schema}


def _sorted_hits(found: dict[int, ChunkHit]) -> list[ChunkHit]:
    return sorted(found.values(), key=lambda h: (-h.score, h.chunk_id))


async def run_agent(question: str, client: ClientSession, llm: Any, settings: Settings, *, today: date,
                    check_upstream: Callable[[], None]) -> Answer:
    s = settings
    # ① 모델이 볼 도구 = MCP가 이 사용자에게 보여 준 도구 그대로. 여기서 목록을 손으로 만들면 권한 겹 ①을 우회한다
    tools = [to_model_tool(t) for t in (await client.list_tools()).tools]
    messages: list[dict] = [{"role": "user", "content": f"오늘 날짜: {today.isoformat()}\n\n질문: {question}"}]
    # ③ 누적: 최종 인용은 루프 전체 조각으로 검증한다. 마지막 호출 결과나 top-k만 남기면
    # 앞선 호출의 조각을 인용한 정상 문장이 invalid_citation이 된다
    found: dict[int, ChunkHit] = {}
    tools_called: list[str] = []

    while True:
        response = await anyio.to_thread.run_sync(lambda: llm.beta.messages.create(
            model=s.generation_model, max_tokens=s.generation_max_tokens, betas=[FALLBACK_BETA], fallbacks="default",
            output_config={"effort": s.generation_effort}, system=agent_prompt(), tools=tools, messages=messages))
        uses = [b for b in response.content if b.type == "tool_use"]
        if not uses:  # ④ 도구 없는 응답 = 최종 답
            raw = "".join(b.text for b in response.content if b.type == "text")
            return replace(verify_citations(raw, _sorted_hits(found)), tools_called=tools_called)
        # 다음 턴에 응답 content를 그대로 돌려준다 — thinking 블록을 빼거나 다시 만들면 API가 400을 낸다
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for use in uses:  # ② tool_use → MCP call_tool
            hits = parse_hits(await client.call_tool(use.name, use.input))
            check_upstream()
            tools_called.append(use.name)
            for h in hits:
                if h.chunk_id not in found or h.score > found[h.chunk_id].score:
                    found[h.chunk_id] = h
            results.append({"type": "tool_result", "tool_use_id": use.id, "content": render_chunks(hits) or NO_RESULTS})
        messages.append({"role": "user", "content": results})
