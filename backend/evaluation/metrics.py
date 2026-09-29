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
    declined = bool({"no_evidence", "refused"} & set(answer.notices)) or is_cannot_answer(answer.text)
    return not answer.sources and declined


def rate(values: Iterable[bool | None]) -> float | None:
    known = [v for v in values if v is not None]
    return sum(known) / len(known) if known else None
