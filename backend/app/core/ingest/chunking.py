"""페이지 → 조각. 조각은 한 페이지 안에서만 만든다(출처 페이지가 하나로 정해지도록)."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

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


TITLE_MAX_CHARS = 60
STRATEGIES = ("fixed", "structure")


def _title(text: str) -> str | None:
    """슬라이드 제목 = 정리된 쪽의 첫 줄 (짧고 조항 제목이 아닐 때만)."""
    first = text.splitlines()[0].strip() if text else ""
    return first if first and len(first) <= TITLE_MAX_CHARS and not SECTION_RE.match(first) else None


def _split_to_fit(text: str, max_chars: int) -> list[str]:
    """줄 경계에서 max_chars 이하로 묶는다. 한 줄이 너무 길면 그 줄만 글자 단위로 자른다. 겹침 없음."""
    pieces: list[str] = []
    current = ""
    for line in text.split("\n"):
        if len(line) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(line[i : i + max_chars] for i in range(0, len(line), max_chars))
        elif current and len(current) + 1 + len(line) > max_chars:
            pieces.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        pieces.append(current)
    return pieces


def chunk_by_structure(pages: Sequence[Page], *, max_chars: int) -> list[ChunkDraft]:
    """구조 기반 분할: 조항이 있으면 조항 경계, 없으면 쪽(=슬라이드) 1장 = 조각 1개. 넘치면 줄 경계로 나눈다.

    section = 조항명 → (이전 쪽에서 이어진 조항) → 슬라이드 제목 순.
    """
    drafts: list[ChunkDraft] = []
    carried: str | None = None
    for page in pages:
        text = page.text.strip()
        if not text:
            continue
        headings = [(m.start(), m.group(1)) for m in SECTION_RE.finditer(text)]
        bounds = [0] + [pos for pos, _ in headings if pos > 0] + [len(text)]
        for start, end in pairwise(bounds):
            segment = text[start:end].strip()
            if not segment:
                continue
            here = [name for pos, name in headings if pos == start]
            section = here[0] if here else (carried or _title(segment))
            for piece in _split_to_fit(segment, max_chars):
                drafts.append(ChunkDraft(page=page.number, section=section, ord=len(drafts), text=piece))
        if headings:
            carried = headings[-1][1]
    return drafts


def build_chunks(pages: Sequence[Page], *, strategy: str, max_chars: int, overlap: int) -> list[ChunkDraft]:
    if strategy == "fixed":
        return chunk_pages(pages, max_chars=max_chars, overlap=overlap)
    if strategy == "structure":
        return chunk_by_structure(pages, max_chars=max_chars)
    raise ValueError(f"unknown chunk strategy: {strategy!r} (choose from {STRATEGIES})")
