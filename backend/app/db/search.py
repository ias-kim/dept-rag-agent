"""권한 겹 2 — 모든 벡터 검색은 이 함수를 거친다. 설계 §4."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass

from sqlalchemy import and_, bindparam, or_, select, text
from sqlalchemy.orm import Session

from app.db.models import SCOPES, Chunk, Document


@dataclass(frozen=True)
class ChunkHit:
    chunk_id: int
    text: str
    source: str
    page: int
    section: str | None
    scope: str
    course_code: str | None
    score: float


def search_chunks(
    session: Session,
    query_vec: Sequence[float],
    *,
    scope: str,
    allowed_courses: Collection[str],
    k: int = 5,
    min_score: float = 0.0,
) -> list[ChunkHit]:
    if isinstance(allowed_courses, str):
        raise TypeError("allowed_courses must be a collection of course codes, not str")
    if scope not in SCOPES:
        raise ValueError(f"unknown scope: {scope!r}")
    # HNSW는 근사 탐색 후 WHERE로 거르므로 필터가 강하면 k개가 안 채워질 수 있다.
    # 필터를 통과한 행이 k개가 될 때까지 계속 스캔하게 한다(pgvector ≥ 0.8). 트랜잭션 한정.
    session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
    distance = Chunk.embedding.cosine_distance(list(query_vec)).label("distance")
    stmt = (
        select(Chunk, Document.path, distance)
        .join(Document, Chunk.document_id == Document.id)
        # 리터럴로 렌더링해야 플래너가 부분 인덱스(WHERE scope = '…')를 고를 수 있다
        .where(Chunk.scope == bindparam("scope", scope, literal_execute=True))
        # 권한 필터: 스코프 조건이 바뀌어도 이 줄이 전공 조각을 막는다
        .where(or_(Chunk.scope == "academic",
                   and_(Chunk.scope == "major", Chunk.course_code.in_(list(allowed_courses)))))
        .where(distance <= 1.0 - min_score)
        .order_by(distance)
        .limit(k)
    )
    return [
        ChunkHit(chunk_id=c.id, text=c.text, source=path, page=c.page, section=c.section,
                 scope=c.scope, course_code=c.course_code, score=1.0 - dist)
        for c, path, dist in session.execute(stmt)
    ]
