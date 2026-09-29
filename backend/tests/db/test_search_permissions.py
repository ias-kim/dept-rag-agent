import pytest

from app.db.models import Chunk, Document
from app.db.search import search_chunks
from tests.fakes import unit


@pytest.fixture
def corpus(session):
    """학사 1, CS101 전공 1, CS202 전공 1 — 모두 같은 방향(unit(0)) + 학사 방향 다른 조각 1."""
    specs = [
        ("academic/a.pdf", "academic", None, 0),
        ("academic/b.pdf", "academic", None, 1),
        ("major/CS101/x.pdf", "major", "CS101", 0),
        ("major/CS202/y.pdf", "major", "CS202", 0),
    ]
    for path, scope, course, axis in specs:
        doc = Document(scope=scope, course_code=course, path=path, sha256="0" * 64)
        session.add(doc)
        session.flush()
        session.add(Chunk(document_id=doc.id, page=1, section=None, ord=0, text=path,
                          embedding=unit(axis), scope=scope, course_code=course))
    session.flush()


def sources(hits):
    return sorted(h.source for h in hits)


def test_enrolled_student_sees_only_own_course(session, corpus):
    hits = search_chunks(session, unit(0), scope="major", allowed_courses={"CS101"})
    assert sources(hits) == ["major/CS101/x.pdf"]


def test_no_enrollment_gets_no_major_chunks(session, corpus):
    assert search_chunks(session, unit(0), scope="major", allowed_courses=set()) == []


def test_foreign_course_request_returns_nothing(session, corpus):
    # MCP 계층이 교집합을 계산한 결과가 비었을 때와 같은 상황
    assert search_chunks(session, unit(0), scope="major", allowed_courses={"CS999"}) == []


def test_academic_is_open_to_everyone(session, corpus):
    hits = search_chunks(session, unit(0), scope="academic", allowed_courses=set())
    assert "academic/a.pdf" in sources(hits)
    assert all(h.scope == "academic" for h in hits)


def test_allowed_courses_is_required_keyword(session, corpus):
    with pytest.raises(TypeError):
        search_chunks(session, unit(0), scope="major")  # type: ignore[call-arg]


def test_min_score_drops_unrelated_chunks(session, corpus):
    hits = search_chunks(session, unit(0), scope="academic", allowed_courses=set(), min_score=0.5)
    assert sources(hits) == ["academic/a.pdf"]
    assert hits[0].score == pytest.approx(1.0)


def test_k_limits_results(session, corpus):
    assert len(search_chunks(session, unit(0), scope="academic", allowed_courses=set(), k=1)) == 1


def test_unknown_scope_rejected(session, corpus):
    with pytest.raises(ValueError):
        search_chunks(session, unit(0), scope="secret", allowed_courses=set())
