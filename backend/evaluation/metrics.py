"""자동 지표 3종 + none 처리. 사람 채점(답변 정확도)은 report.py가 grading CSV에서 읽는다."""

import unicodedata
from collections.abc import Iterable, Sequence

from app.core.answer import Answer, Source, is_cannot_answer
from app.db.search import ChunkHit
from evaluation.dataset import EvalItem


def _gold(item: EvalItem) -> set[tuple[str, int]]:
    return {(g.file, g.page) for g in item.gold_sources}


def recall_at_k(item: EvalItem, retrieved: Sequence[ChunkHit]) -> bool | None:
    if item.intent == "none":
        return None
    gold = _gold(item)
    for h in retrieved:
        normalized_source = unicodedata.normalize("NFC", h.source)
        if (normalized_source, h.page) in gold:
            return True
    return False


def source_match(item: EvalItem, sources: Sequence[Source]) -> bool | None:
    if item.intent == "none":
        return None
    gold = _gold(item)
    for s in sources:
        normalized_file = unicodedata.normalize("NFC", s.file)
        if (normalized_file, s.page) in gold:
            return True
    return False


def none_handled(item: EvalItem, answer: Answer) -> bool | None:
    """none 문항: 출처를 내지 않았고 + 거절/근거없음 공지가 있거나 "찾을 수 없다"고 답해야 통과."""
    if item.intent != "none":
        return None
    # out_of_scope: workflow가 none 의도를 검색·생성 없이 거절한 경우. 빠지면 라우터가 잘 거절해도 실패로 집계된다
    declined = bool({"no_evidence", "refused", "out_of_scope"} & set(answer.notices)) or is_cannot_answer(answer.text)
    # 도구 장애로 근거가 0건이 되어 붙은 no_evidence를 '잘 거절했다'로 세면 장애가 점수를 올린다
    if count_tool_errors(answer) > 0:
        return False
    return not answer.sources and declined


def count_tool_errors(answer: Answer) -> int:
    return sum(1 for n in answer.notices if n.startswith("tool_error:"))


def intent_ok(item: EvalItem, answer: Answer) -> bool | None:
    """workflow 실행만 채점. 형식 오류로 both가 된 경우는 정답 라벨이 both여도 오답(설계 §5)."""
    if answer.intent is None:
        return None
    return bool(answer.intent_valid) and answer.intent == item.intent


def routing_loss(record: dict) -> bool | None:
    """오분류 때문에 근거를 놓친 문항인가. 의도 정확도만 보면 피해 없는 오분류(academic→both 등)까지 같은 무게로 센다."""
    if record.get("intent_ok") is None:
        return None
    return record["intent_ok"] is False and record["recall_at_k"] is False


def rate(values: Iterable[bool | None]) -> float | None:
    known = [v for v in values if v is not None]
    return sum(known) / len(known) if known else None
