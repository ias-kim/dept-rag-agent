import pytest
from sqlalchemy import func, select

from app.core.ingest.sync import sync_folder
from app.db.models import Chunk, Document
from tests.fakes import FakeEmbedder, make_pdf

OPTS = {"max_chars": 800, "overlap": 100}


@pytest.fixture
def root(tmp_path):
    make_pdf(tmp_path / "academic" / "calendar.pdf", ["Registration Sep 8", "Grades Dec 20"])
    make_pdf(tmp_path / "academic" / "rules.pdf", ["Article 1 Purpose"])
    make_pdf(tmp_path / "major" / "cs101" / "lec1.pdf", ["Stacks and queues"])
    return tmp_path


def chunk_count(session, path=None):
    stmt = select(func.count()).select_from(Chunk).join(Document, Chunk.document_id == Document.id)
    if path:
        stmt = stmt.where(Document.path == path)
    return session.execute(stmt).scalar_one()


def test_first_sync_adds_everything(session, root):
    report = sync_folder(session, root, FakeEmbedder(), **OPTS)
    assert sorted(report.added) == ["academic/calendar.pdf", "academic/rules.pdf", "major/cs101/lec1.pdf"]
    assert chunk_count(session) == 4


def test_course_folder_is_uppercased(session, root):
    sync_folder(session, root, FakeEmbedder(), **OPTS)
    doc = session.scalars(select(Document).where(Document.path == "major/cs101/lec1.pdf")).one()
    assert (doc.scope, doc.course_code) == ("major", "CS101")


def test_second_sync_is_noop_without_embedding(session, root):
    sync_folder(session, root, FakeEmbedder(), **OPTS)
    embedder = FakeEmbedder()
    report = sync_folder(session, root, embedder, **OPTS)
    assert len(report.unchanged) == 3 and not (report.added or report.updated or report.removed)
    assert embedder.calls == 0


def test_changed_file_replaces_its_chunks(session, root):
    sync_folder(session, root, FakeEmbedder(), **OPTS)
    make_pdf(root / "academic" / "rules.pdf", ["Article 1 Purpose", "Article 2 Scope", "Article 3 Terms"])
    report = sync_folder(session, root, FakeEmbedder(), **OPTS)
    assert report.updated == ["academic/rules.pdf"]
    assert chunk_count(session, "academic/rules.pdf") == 3


def test_deleted_file_removes_chunks(session, root):
    sync_folder(session, root, FakeEmbedder(), **OPTS)
    (root / "academic" / "calendar.pdf").unlink()
    report = sync_folder(session, root, FakeEmbedder(), **OPTS)
    assert report.removed == ["academic/calendar.pdf"]
    assert chunk_count(session, "academic/calendar.pdf") == 0


def test_empty_pdf_is_reported(session, root):
    make_pdf(root / "academic" / "scan.pdf", [""])
    report = sync_folder(session, root, FakeEmbedder(), **OPTS)
    assert report.empty == ["academic/scan.pdf"]
    assert "scan.pdf" in report.summary()


def test_misplaced_pdf_rejected_before_any_change(session, root):
    make_pdf(root / "major" / "loose.pdf", ["No course folder"])
    with pytest.raises(ValueError, match="major/loose.pdf"):
        sync_folder(session, root, FakeEmbedder(), **OPTS)
    assert session.execute(select(func.count()).select_from(Document)).scalar_one() == 0


def test_embedder_failure_rolls_back_everything(session, root):
    with pytest.raises(RuntimeError):
        sync_folder(session, root, FakeEmbedder(fail_on_call=2), **OPTS)
    assert session.execute(select(func.count()).select_from(Document)).scalar_one() == 0
    assert chunk_count(session) == 0


def test_non_pdf_files_are_ignored(session, root):
    (root / "academic" / ".DS_Store").write_bytes(b"x")
    report = sync_folder(session, root, FakeEmbedder(), **OPTS)
    assert len(report.added) == 3


def test_missing_root_rejected_before_any_change(session, root):
    sync_folder(session, root, FakeEmbedder(), **OPTS)
    with pytest.raises(ValueError, match="자료 폴더"):
        sync_folder(session, root / "nope", FakeEmbedder(), **OPTS)
    assert session.execute(select(func.count()).select_from(Document)).scalar_one() == 3
