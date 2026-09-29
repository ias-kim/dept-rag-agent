import pytest

from app.core.ingest.chunking import ChunkDraft, chunk_pages
from app.core.ingest.pdf import Page


def test_short_page_is_one_chunk():
    assert chunk_pages([Page(3, "짧은 공지")], max_chars=800, overlap=100) == [
        ChunkDraft(page=3, section=None, ord=0, text="짧은 공지")
    ]


def test_long_page_splits_with_overlap():
    text = "".join(str(i % 10) for i in range(2000))
    drafts = chunk_pages([Page(1, text)], max_chars=800, overlap=100)
    assert [len(d.text) for d in drafts] == [800, 800, 600]
    assert drafts[0].text[-100:] == drafts[1].text[:100]
    assert [d.ord for d in drafts] == [0, 1, 2]


def test_empty_pages_skipped_and_ord_continues():
    drafts = chunk_pages([Page(1, "가"), Page(2, "   "), Page(3, "나")], max_chars=800, overlap=100)
    assert [(d.page, d.ord) for d in drafts] == [(1, 0), (3, 1)]


def test_article_heading_becomes_section_and_carries_over():
    pages = [Page(1, "학칙 안내\n제1조(목적) 이 규정은 수강신청을 정한다."), Page(2, "계속되는 내용")]
    drafts = chunk_pages(pages, max_chars=800, overlap=100)
    assert [d.section for d in drafts] == ["제1조(목적)", "제1조(목적)"]


def test_later_heading_replaces_section():
    pages = [Page(1, "제1조(목적) 가"), Page(2, "제2조(기간) 나")]
    assert [d.section for d in chunk_pages(pages, max_chars=800, overlap=100)] == ["제1조(목적)", "제2조(기간)"]


def test_overlap_must_be_smaller_than_max():
    with pytest.raises(ValueError):
        chunk_pages([Page(1, "가")], max_chars=100, overlap=100)
