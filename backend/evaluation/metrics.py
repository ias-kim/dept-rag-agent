"""자동 지표 3종 + none 처리. 사람 채점(답변 정확도)은 report.py가 grading CSV에서 읽는다."""

from collections.abc import Iterable, Sequence

from app.core.answer import Source
from app.db.search import ChunkHit
from evaluation.dataset import EvalItem


def _gold(item: EvalItem) -> set[tuple[str, int]]:
    return {(g.file, g.page) for g in item.gold_sources}


def recall_at_k(item: EvalItem, retrieved: Sequence[ChunkHit]) -> bool | None:
    if item.intent == "none":
        return None
    return any((h.source, h.page) in _gold(item) for h in retrieved)


def source_match(item: EvalItem, sources: Sequence[Source]) -> bool | None:
    if item.intent == "none":
        return None
    return any((s.file, s.page) in _gold(item) for s in sources)


def none_handled(item: EvalItem, sources: Sequence[Source]) -> bool | None:
    if item.intent != "none":
        return None
    return not sources


def rate(values: Iterable[bool | None]) -> float | None:
    known = [v for v in values if v is not None]
    return sum(known) / len(known) if known else None
