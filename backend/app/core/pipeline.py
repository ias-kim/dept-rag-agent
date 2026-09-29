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
