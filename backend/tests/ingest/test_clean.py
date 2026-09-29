from app.core.ingest.clean import clean_pages
from app.core.ingest.pdf import Page

HEADER = "영진전문대 글로벌시스템융합과 정영철 교수,"


def slide(n: int, body: str, header: str = HEADER) -> Page:
    return Page(n, f"{header}\n{body}\n{n}")


def test_repeated_header_and_page_numbers_are_removed():
    pages = [slide(i, f"슬라이드 {i} 제목\n본문 {i}") for i in range(1, 7)]
    cleaned = clean_pages(pages)
    assert cleaned[0] == Page(1, "슬라이드 1 제목\n본문 1")
    assert all(HEADER not in p.text for p in cleaned)


def test_header_variants_with_page_number_attached_are_removed():
    headers = [HEADER, f"2{HEADER}", f"{HEADER} 3", HEADER, f"{HEADER} 5"]
    pages = [slide(i + 1, f"제목 {i}", header=h) for i, h in enumerate(headers)]
    assert all("정영철" not in p.text for p in clean_pages(pages))


def test_numbered_titles_that_are_not_page_numbers_are_kept():
    # "Chapter 7"이 7쪽이 아닌 곳에 반복돼도 머리글로 보지 않는다 (쪽번호와 같은 숫자만 뗀다)
    pages = [Page(i, f"Chapter {i + 10}\n본문 {i}") for i in range(1, 6)]
    assert [p.text.splitlines()[0] for p in clean_pages(pages)] == [f"Chapter {i + 10}" for i in range(1, 6)]


def test_page_number_only_lines_are_removed():
    pages = [Page(1, "- 3 -\n본문"), Page(2, "본문\n3 / 55"), Page(3, "12\n본문")]
    assert [p.text for p in clean_pages(pages)] == ["본문", "본문", "본문"]


def test_short_repeated_lines_like_code_braces_are_kept():
    pages = [Page(i, f"def f{i}():\n    return {i}\n}}") for i in range(1, 6)]
    assert all(p.text.endswith("}") for p in clean_pages(pages))


def test_repeated_line_in_the_middle_of_a_page_is_kept():
    pages = [Page(i, f"제목 {i}\n첫 줄\n두 번째 줄\n반복되는 본문 문장입니다\n셋째\n넷째\n끝 {i}") for i in range(1, 6)]
    assert all("반복되는 본문 문장입니다" in p.text for p in clean_pages(pages))


def test_short_document_keeps_header():
    pages = [slide(1, "제목"), slide(2, "제목2")]
    assert all(HEADER in p.text for p in clean_pages(pages))


def test_empty_pages_stay_empty():
    pages = [slide(1, "a"), Page(2, ""), slide(3, "b"), slide(4, "c")]
    assert clean_pages(pages)[1] == Page(2, "")
