"""4주차 워크플로우 라우터 — 설계 §5.

분류(LLM)는 질문만 보고 의도를 고르고, 처리 표(코드)가 사용자 권한을 반영해 도구를 정한다.
분류기에 역할·수강 과목을 넣으면 "나는 수강생이야" 같은 질문 문구로 권한이 흔들릴 수 있으므로 넣지 않는다.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.mcp.server import TOOL_ACADEMIC, TOOL_MAJOR, UserContext

INTENTS = ("major", "academic", "both", "none")
PROMPT_PATH = Path(__file__).parent / "prompts" / "classify.md"
NEEDS_ENROLLMENT = "major_requires_enrollment"
OUT_OF_SCOPE = "out_of_scope"
FALLBACK_INTENT = "both"  # 분류 실패 시 두 색인 모두 검색 — 답은 놓치지 않되 평가에서는 오답으로 센다


@dataclass(frozen=True)
class Classification:
    intent: str
    valid: bool  # False = 형식 오류·거절로 FALLBACK_INTENT 대체. True로 잘못 두면 의도 정확도가 부풀려진다
    raw: str


@dataclass(frozen=True)
class Plan:
    tools: tuple[str, ...]
    notices: tuple[str, ...]


def classify_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def classify_prompt_hash() -> str:
    """평가 실행 기록에 남겨, 프롬프트가 바뀐 실행끼리 비교하는 실수를 막는다."""
    return hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()[:12]


def parse_intent(text: str) -> str | None:
    """라벨 한 단어만 인정한다. "academic because …"를 받아 주면 설명 붙은 출력이 정답으로 집계된다."""
    word = text.strip().rstrip(".").strip().lower()
    return word if word in INTENTS else None


def classify(llm: Any, question: str, *, model: str, max_tokens: int) -> Classification:
    response = llm.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=classify_prompt(),
        messages=[{"role": "user", "content": question}],  # 질문만 — 역할·과목을 넣지 않는다
    )
    if response.stop_reason == "refusal":  # 거절 응답의 content는 읽지 않는다
        return Classification(FALLBACK_INTENT, False, "")
    raw = "".join(block.text for block in response.content if block.type == "text").strip()
    intent = parse_intent(raw)
    return Classification(intent or FALLBACK_INTENT, intent is not None, raw)


def plan(intent: str, user: UserContext) -> Plan:
    """처리 표: 의도 × 수강 여부 → 호출할 도구. 권한 판단은 여기(코드)에서만 한다.

    여기서 미수강자에게 TOOL_MAJOR를 내주더라도 MCP 권한 두 겹이 막지만, 그러면 불필요한 거절 호출과
    "왜 전공 자료가 없는지" 안내가 사라진다.
    """
    is_enrolled = bool(user.courses)
    if intent == "academic":
        return Plan((TOOL_ACADEMIC,), ())
    if intent == "major":
        return Plan((TOOL_MAJOR,), ()) if is_enrolled else Plan((), (NEEDS_ENROLLMENT,))
    if intent == "both":
        if is_enrolled:
            return Plan((TOOL_ACADEMIC, TOOL_MAJOR), ())
        return Plan((TOOL_ACADEMIC,), (NEEDS_ENROLLMENT,))
    if intent == "none":
        return Plan((), (OUT_OF_SCOPE,))
    raise ValueError(f"알 수 없는 의도: {intent!r}")
