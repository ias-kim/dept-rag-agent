from collections.abc import Sequence
from pathlib import Path

from fpdf import FPDF

from app.db.models import EMBEDDING_DIM


def unit(i: int) -> list[float]:
    """i번 축만 1인 단위 벡터. 같은 i끼리 코사인 거리 0, 다른 i끼리 1."""
    v = [0.0] * EMBEDDING_DIM
    v[i % EMBEDDING_DIM] = 1.0
    return v


def make_pdf(path: Path, pages: Sequence[str]) -> Path:
    """테스트용 PDF. 한국어 폰트가 없으므로 ASCII만 쓴다. 빈 문자열이면 텍스트 없는 페이지."""
    pdf = FPDF()
    pdf.set_font("Helvetica", size=12)
    for text in pages:
        pdf.add_page()
        if text:
            pdf.multi_cell(0, 8, text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(pdf.output()))
    return path
