"""답변 생성과 출처 검증 — 설계 결정 4.

출처 문자열은 LLM이 쓴 텍스트가 아니라 조각 메타데이터(ChunkHit)로 코드가 만든다.
"""

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import anthropic

from app.core.config import Settings
from app.db.search import ChunkHit

PROMPT_PATH = Path(__file__).parent / "prompts" / "answer.md"
# 인용처럼 보이는 모든 표기(반각·전각 괄호, 목록형, 소문자, 군더더기 포함)
MARKER_RE = re.compile(r"[\[［]\s*[Cc]\s*\d+[^\]］]*[\]］]")
# 코드가 인정하는 정상 표기: [C7] · [C7, C12] · [C7, 12]
VALID_MARKER_RE = re.compile(r"\[\s*C\d+(?:\s*,\s*C?\d+)*\s*\]")
PLAIN_NUMBER_RE = re.compile(r"\[(\d+)\]")
CANNOT_ANSWER = "제공된 자료에서 답을 찾을 수 없습니다"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
NO_EVIDENCE = "관련 자료를 찾지 못했습니다. 질문을 조금 더 구체적으로 해 주세요."
REFUSED = "이 질문에는 답변할 수 없습니다."
EMPTY = "답변을 만들지 못했습니다. 잠시 후 다시 시도해 주세요."


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
    # 자료에 원래 있던 [1] 같은 표기가 재번호된 인용과 섞이지 않게 전각으로 바꾼다
    raw = PLAIN_NUMBER_RE.sub(lambda m: f"［{m.group(1)}］", raw)

    def replace(m: re.Match[str]) -> str:
        nonlocal invalid
        marker = m.group(0)
        if not VALID_MARKER_RE.fullmatch(marker):
            invalid = True
            return ""
        numbers = []
        for cid in (int(n) for n in re.findall(r"\d+", marker)):
            if cid not in by_id:
                invalid = True
                continue
            if cid not in order:
                order.append(cid)
            numbers.append(order.index(cid) + 1)
        return "".join(f"[{n}]" for n in numbers)

    text = MARKER_RE.sub(replace, raw).strip()
    sources = [Source(by_id[c].source, by_id[c].page, by_id[c].section) for c in order]
    notices = ["invalid_citation"] if invalid else []
    if not sources and CANNOT_ANSWER not in text:
        notices.append("no_citation")
        invalid = True
    return Answer(text=text, sources=sources, citation_ok=not invalid, notices=notices, retrieved=list(hits))


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
    if not raw.strip():
        return Answer(text=EMPTY, sources=[], citation_ok=True, notices=["empty"], retrieved=list(hits))
    answer = verify_citations(raw, hits)
    if response.stop_reason == "max_tokens":
        answer = replace(answer, notices=answer.notices + ["truncated"])
    return answer
