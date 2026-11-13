"""이어지는 대화 — 후속 질문을 검색 가능한 독립 질문으로 다시 쓴다.

"원격이랑 로컬은 뭐가 달라?"를 그대로 임베딩하면 무엇의 원격·로컬인지 몰라 엉뚱한 공지가 잡힌다(유사도 0.15).
앞 대화를 붙여 "MCP 원격 서버와 로컬 서버의 차이"로 바꾸면 해당 강의자료가 잡힌다(0.60, 2026-11-13 실측).
그래서 이력은 답변 프롬프트가 아니라 **검색 전 질문 재작성**에 쓴다. 재작성한 질문이 분류·검색·생성을 모두 지난다.

이력은 클라이언트가 보낸 값이라 믿지 않는다. 바꿀 수 있는 것은 본인 질문의 검색어뿐이고,
무엇을 검색할 수 있는지(권한)는 여전히 UserContext·SQL 조건이 정한다.
"""

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROMPT_PATH = Path(__file__).parent / "prompts" / "condense.md"
# 재작성에 넣는 최근 턴 수. API 상한(routes.HISTORY_MAX_TURNS)과 같게 둔다 — 더 넣으면 비용만 늘고 오래된 주제가 섞인다
RECENT_TURNS = 6
# 재작성 결과 상한. 검색어 상한(agent.QUERY_MAX_CHARS)과 같다 — 넘으면 임베딩이 4xx로 실패해 500이 되고 한도도 못 돌려받는다
CONDENSED_MAX_CHARS = 500
CITATION_RE = re.compile(r"\[\d+\]")
LABEL_RE = re.compile(r"^(?:독립\s*)?질문\s*[:：]\s*")
QUOTES = "\"'“”‘’「」『』"


@dataclass(frozen=True)
class Turn:
    question: str
    answer: str


def condense_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def condense_prompt_hash() -> str:
    return hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()[:12]


def render_history(history: Sequence[Turn]) -> str:
    # 이전 답변의 [1] 번호는 그 답변의 출처 목록에서만 뜻이 있다 — 남기면 재작성 모델이 검색어에 숫자를 섞는다
    return "\n\n".join(f"학생: {t.question}\n도우미: {CITATION_RE.sub('', t.answer).strip()}"
                       for t in history[-RECENT_TURNS:])


def _clean(text: str) -> str:
    text = LABEL_RE.sub("", text.strip().splitlines()[0].strip() if text.strip() else "")
    return text.strip().strip(QUOTES).strip()


def condense_question(llm: Any, question: str, history: Sequence[Turn], *, model: str, max_tokens: int) -> str:
    """재작성이 실패하면(거절·빈 출력·너무 김) 원래 질문을 쓴다. 대화 맥락만 잃을 뿐 질문 자체는 막지 않는다."""
    response = llm.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=condense_prompt(),
        messages=[{"role": "user", "content": f"<앞 대화>\n{render_history(history)}\n</앞 대화>\n\n새 질문: {question}"}],
    )
    if response.stop_reason == "refusal":  # 거절 응답의 content는 읽지 않는다
        return question
    rewritten = _clean("".join(b.text for b in response.content if b.type == "text"))
    if not rewritten or len(rewritten) > CONDENSED_MAX_CHARS:
        return question
    return rewritten
