import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.db.models import EMBEDDING_DIM
from tests.fakes import unit

INSERT_DOC = "INSERT INTO documents (scope, course_code, path, sha256) VALUES (:s, :c, :p, :h) RETURNING id"
INSERT_CHUNK = (
    "INSERT INTO chunks (document_id, page, section, ord, text, embedding, scope, course_code) "
    "VALUES (:d, 1, NULL, 0, 't', CAST(:e AS vector), :s, :c)"
)


def add_doc(session, scope, course, path="a.pdf"):
    return session.execute(sa.text(INSERT_DOC), {"s": scope, "c": course, "p": path, "h": "0" * 64}).scalar_one()


def add_chunk(session, doc_id, scope, course):
    session.execute(sa.text(INSERT_CHUNK), {"d": doc_id, "e": str(unit(0)), "s": scope, "c": course})


@pytest.mark.parametrize("scope, course", [("major", None), ("academic", "CS101"), ("other", None)])
def test_document_scope_course_rule(session, scope, course):
    with pytest.raises(IntegrityError):
        add_doc(session, scope, course)


def test_course_code_must_be_uppercase(session):
    with pytest.raises(IntegrityError):
        add_doc(session, "major", "cs101")


def test_chunk_scope_must_match_document(session):
    doc = add_doc(session, "academic", None)
    with pytest.raises(IntegrityError):
        add_chunk(session, doc, "major", "CS101")


def test_major_chunk_course_must_match_document(session):
    doc = add_doc(session, "major", "CS101")
    with pytest.raises(IntegrityError):
        add_chunk(session, doc, "major", "CS202")


def test_deleting_document_cascades_to_chunks(session):
    doc = add_doc(session, "major", "CS101")
    add_chunk(session, doc, "major", "CS101")
    session.execute(sa.text("DELETE FROM documents WHERE id = :d"), {"d": doc})
    assert session.execute(sa.text("SELECT count(*) FROM chunks")).scalar_one() == 0


def test_embedding_dimension_matches_constant(session):
    typmod = session.execute(
        sa.text("SELECT atttypmod FROM pg_attribute WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'")
    ).scalar_one()
    assert typmod == EMBEDDING_DIM


def test_two_partial_vector_indexes(session):
    rows = session.execute(
        sa.text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'chunks' AND indexdef LIKE '%hnsw%'")
    ).all()
    defs = {name: d for name, d in rows}
    assert set(defs) == {"chunks_major_hnsw", "chunks_academic_hnsw"}
    assert "'major'" in defs["chunks_major_hnsw"] and "'academic'" in defs["chunks_academic_hnsw"]
