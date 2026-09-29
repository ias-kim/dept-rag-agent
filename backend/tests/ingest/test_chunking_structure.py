import pytest

from app.core.ingest.chunking import STRATEGIES, build_chunks, chunk_by_structure
from app.core.ingest.pdf import Page


def test_slide_page_is_one_chunk_titled_by_first_line():
    drafts = chunk_by_structure([Page(4, "Decorator란?\n함수를 감싸 기능을 더한다.\n@wraps 사용")], max_chars=800)
    assert [(d.page, d.section, d.ord) for d in drafts] == [(4, "Decorator란?", 0)]
    assert drafts[0].text.startswith("Decorator란?")


def test_articles_split_at_headings():
    text = "학칙 안내\n제1조(목적) 이 규정은 수강을 정한다.\n제2조(기간) 정정은 9월 8일부터다."
    drafts = chunk_by_structure([Page(1, text)], max_chars=800)
    assert [d.section for d in drafts] == ["학칙 안내", "제1조(목적)", "제2조(기간)"]
    assert drafts[2].text == "제2조(기간) 정정은 9월 8일부터다."


def test_article_carries_to_next_page_without_heading():
    pages = [Page(1, "제3조(휴학) 휴학은 2학기까지다."), Page(2, "다만 군 휴학은 예외로 한다.")]
    assert [d.section for d in chunk_by_structure(pages, max_chars=800)] == ["제3조(휴학)", "제3조(휴학)"]


def test_long_page_splits_at_line_boundaries_without_overlap():
    lines = [f"{i:03d} " + "가" * 95 for i in range(20)]  # 20줄 × 100자
    drafts = chunk_by_structure([Page(1, "\n".join(lines))], max_chars=800)
    assert all(len(d.text) <= 800 for d in drafts)
    assert "\n".join(d.text for d in drafts) == "\n".join(lines)
    assert [d.ord for d in drafts] == list(range(len(drafts)))


def test_single_line_longer_than_max_is_hard_split():
    drafts = chunk_by_structure([Page(1, "가" * 1700)], max_chars=800)
    assert [len(d.text) for d in drafts] == [800, 800, 100]


def test_long_first_line_is_not_a_title():
    drafts = chunk_by_structure([Page(1, "가" * 61 + "\n본문")], max_chars=800)
    assert drafts[0].section is None


def test_empty_pages_skipped():
    drafts = chunk_by_structure([Page(1, "제목\n본문"), Page(2, "  "), Page(3, "제목3")], max_chars=800)
    assert [(d.page, d.ord) for d in drafts] == [(1, 0), (3, 1)]


def test_build_chunks_dispatches_by_strategy():
    pages = [Page(1, "제목\n" + "가" * 1000)]
    assert set(STRATEGIES) == {"fixed", "structure"}
    fixed = build_chunks(pages, strategy="fixed", max_chars=800, overlap=100)
    structure = build_chunks(pages, strategy="structure", max_chars=800, overlap=100)
    assert fixed[1].text[:100] == fixed[0].text[-100:]  # 고정 길이는 겹침이 있다
    assert structure[0].section == "제목"
    with pytest.raises(ValueError, match="strategy"):
        build_chunks(pages, strategy="nope", max_chars=800, overlap=100)
