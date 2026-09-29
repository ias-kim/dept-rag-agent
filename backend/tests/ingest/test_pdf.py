from app.core.ingest.pdf import Page, extract_pages
from tests.fakes import make_pdf


def test_extract_pages_numbers_from_one(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", ["Article 1 Purpose", "Article 2 Period"])
    assert extract_pages(pdf) == [Page(1, "Article 1 Purpose"), Page(2, "Article 2 Period")]


def test_blank_page_yields_empty_text(tmp_path):
    pdf = make_pdf(tmp_path / "b.pdf", [""])
    assert extract_pages(pdf) == [Page(1, "")]
