"""페이지 → 조각. 조각은 한 페이지 안에서만 만든다(출처 페이지가 하나로 정해지도록)."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.core.ingest.pdf import Page

SECTION_RE = re.compile(r"^\s*(제\s*\d+\s*조(?:\s*\([^)]*\))?)", re.MULTILINE)


@dataclass(frozen=True)
class ChunkDraft:
    page: int
    section: str | None
    ord: int
    text: str


def chunk_pages(pages: Sequence[Page], *, max_chars: int, overlap: int) -> list[ChunkDraft]:
    if not 0 <= overlap < max_chars:
        raise ValueError("overlap must be in [0, max_chars)")
    drafts: list[ChunkDraft] = []
    carried: str | None = None
    for page in pages:
        text = page.text.strip()
        if not text:
            continue
        headings = [(m.start(), m.group(1)) for m in SECTION_RE.finditer(text)]
        start = 0
        while start < len(text):
            end = min(start + max_chars, len(text))
            # 조각이 시작되는 지점의 조항을 쓴다. 시작 시점에 조항이 없으면 조각 안의 첫 조항.
            at_start = [name for pos, name in headings if pos <= start]
            inside = [name for pos, name in headings if start < pos < end]
            section = at_start[-1] if at_start else (carried or (inside[0] if inside else None))
            drafts.append(ChunkDraft(page=page.number, section=section, ord=len(drafts), text=text[start:end]))
            if end == len(text):
                break
            start = end - overlap
        if headings:
            carried = headings[-1][1]
    return drafts
