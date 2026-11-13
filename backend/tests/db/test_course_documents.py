"""과목별 강의자료 목록 — 목록 조회도 권한 겹 ②(SQL 수강 조건)를 지난다."""

from app.db.documents import list_course_documents
from tests.fakes import seed_chunks


def test_lists_only_documents_of_allowed_course(session):
    seed_chunks(session, [("major/AGENT/b.pdf", "major", "AGENT", 0), ("major/AGENT/a.pdf", "major", "AGENT", 0),
                          ("major/WEB/c.pdf", "major", "WEB", 0), ("academic/x.md", "academic", None, 0)])
    docs = list_course_documents(session, "AGENT", allowed_courses=frozenset({"AGENT"}))
    assert [(d.file, d.pages) for d in docs] == [("a.pdf", 1), ("b.pdf", 1)]


def test_course_outside_allowed_returns_nothing_even_if_called_directly(session):
    # API 검사를 빼먹은 새 호출자가 생겨도 남의 과목 목록이 나오지 않게 SQL에서 한 번 더 막는다
    seed_chunks(session, [("major/WEB/c.pdf", "major", "WEB", 0)])
    assert list_course_documents(session, "WEB", allowed_courses=frozenset({"AGENT"})) == []


def test_pages_is_highest_page_of_document(session):
    from app.db.models import Chunk, Document
    from tests.fakes import unit
    doc = Document(scope="major", course_code="AGENT", path="major/AGENT/long.pdf", sha256="0" * 64)
    session.add(doc)
    session.flush()
    session.add_all(Chunk(document_id=doc.id, page=p, section=None, ord=p, text="t", embedding=unit(0),
                          scope="major", course_code="AGENT") for p in (1, 7, 3))
    session.flush()
    assert [(d.file, d.pages) for d in list_course_documents(session, "AGENT", allowed_courses={"AGENT"})] == [("long.pdf", 7)]
