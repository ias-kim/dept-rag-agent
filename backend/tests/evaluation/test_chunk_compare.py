from app.core.ingest.pdf import Page
from evaluation.chunk_compare import ends_mid_line, render, summarize

SLIDE_DOC = [Page(1, "Closure\n" + "\n".join(["함수가 선언된 환경을 기억한다."] * 3)),
             Page(2, "Scope\n" + "가" * 1000)]


def test_ends_mid_line():
    page = "첫 줄입니다\n둘째 줄"
    assert ends_mid_line("첫 줄입니다", page) is False
    assert ends_mid_line("첫 줄", page) is True
    assert ends_mid_line("둘째 줄", page) is False  # 쪽의 끝


def test_summarize_structure_vs_fixed():
    structure = summarize([SLIDE_DOC], strategy="structure", max_chars=800, overlap=100)
    fixed = summarize([SLIDE_DOC], strategy="fixed", max_chars=800, overlap=100)
    assert structure["docs"] == 1 and structure["pages"] == 2
    # 1쪽 1조각 + 2쪽은 "Scope" 줄, 1,000자 줄을 800+200으로 → 2쪽 3조각, 합계 4 (제목만 남는 작은 조각은 tiny 지표로 드러남)
    assert structure["chunks"] == 4
    assert structure["tiny"] > 0
    assert structure["with_section"] == 1.0
    assert fixed["chunks"] == 3 and fixed["with_section"] == 0.0
    assert fixed["mid_line_cut"] > 0 and structure["mid_line_cut"] > 0  # 2쪽은 한 줄이 800자 초과
    assert structure["avg_chars"] > 0 and structure["p90_chars"] >= structure["avg_chars"]


def test_render_is_deterministic_and_aggregate_only():
    rows = {s: summarize([SLIDE_DOC], strategy=s, max_chars=800, overlap=100) for s in ("fixed", "structure")}
    text = render(rows, max_chars=800, overlap=100)
    assert text == render(rows, max_chars=800, overlap=100)
    assert text.startswith("<!-- DO NOT EDIT")
    assert "함수가 선언된" not in text  # 원문이 들어가지 않는다 (레포 PUBLIC)
    assert "| fixed |" in text and "| structure |" in text
