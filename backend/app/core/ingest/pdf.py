from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass(frozen=True)
class Page:
    number: int
    text: str


def extract_pages(path: Path) -> list[Page]:
    reader = PdfReader(path)
    return [Page(i + 1, (page.extract_text() or "").strip()) for i, page in enumerate(reader.pages)]
