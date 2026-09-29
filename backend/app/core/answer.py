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
