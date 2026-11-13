"""과목별 강의자료 목록 — 화면의 "이 과목 강의자료" 패널용.

목록도 권한 겹 ②다. 파일명만 보여도 남의 과목 수업 구성이 드러나므로, 호출자가 수강 검사를 빼먹어도
SQL 조건이 미수강 과목을 막는다(search_chunks와 같은 원칙).
"""

from collections.abc import Collection
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document


@dataclass(frozen=True)
class CourseDocument:
    file: str  # 파일명만. 적재 경로 전체(major/<코드>/…)는 서버 내부 구조라 내보내지 않는다
    pages: int  # 조각이 있는 가장 큰 쪽 번호. 텍스트 없는 끝쪽은 세지 않는다


def list_course_documents(session: Session, course_code: str, *,
                          allowed_courses: Collection[str]) -> list[CourseDocument]:
    if isinstance(allowed_courses, str):
        raise TypeError("allowed_courses must be a collection of course codes, not str")
    stmt = (
        select(Document.path, func.max(Chunk.page))
        .join(Chunk, Chunk.document_id == Document.id)
        .where(Document.scope == "major", Document.course_code == course_code)
        # 권한 필터: 위 조건이 바뀌어도 이 줄이 미수강 과목의 자료 목록을 막는다
        .where(Document.course_code.in_(list(allowed_courses)))
        .group_by(Document.id, Document.path)
    )
    docs = [CourseDocument(path.rsplit("/", 1)[-1], pages) for path, pages in session.execute(stmt)]
    return sorted(docs, key=lambda d: d.file)
