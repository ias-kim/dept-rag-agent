from app.core.ingest.markdown import extract_markdown
from app.core.ingest.pdf import Page


def write(tmp_path, text):
    path = tmp_path / "notice.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_each_h2_section_becomes_a_page_with_heading_first(tmp_path):
    path = write(tmp_path, "## 캡스톤디자인(II)\n- 금 1~6교시\n\n## 딥러닝이론과실습\n- 화 3~4교시\n")
    assert extract_markdown(path) == [
        Page(1, "캡스톤디자인(II)\n- 금 1~6교시"),
        Page(2, "딥러닝이론과실습\n- 화 3~4교시"),
    ]


def test_preamble_before_first_h2_is_its_own_page(tmp_path):
    path = write(tmp_path, "# 2026학년도 2학기 시간표\n교시: 1교시 9:00\n\n## 월요일\n- 1학년 일본어 특강\n")
    assert extract_markdown(path) == [
        Page(1, "2026학년도 2학기 시간표\n교시: 1교시 9:00"),
        Page(2, "월요일\n- 1학년 일본어 특강"),
    ]


def test_text_without_headings_is_one_page(tmp_path):
    path = write(tmp_path, "추석 연휴 9/24~25 강의실 폐쇄\n")
    assert extract_markdown(path) == [Page(1, "추석 연휴 9/24~25 강의실 폐쇄")]


def test_h3_stays_inside_its_h2_section(tmp_path):
    path = write(tmp_path, "## 수요일\n### 2학년\n- 데이터구조\n")
    assert extract_markdown(path) == [Page(1, "수요일\n2학년\n- 데이터구조")]


def test_empty_file_has_no_pages(tmp_path):
    assert extract_markdown(write(tmp_path, "\n\n")) == []
