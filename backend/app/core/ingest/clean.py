"""머리글·꼬리말 제거 — 한 문서 안에서 여러 쪽의 가장자리(첫·끝 2줄)에 반복되는 줄과 쪽번호 줄을 지운다.

교수명·학교명 같은 값을 코드에 두지 않는다. 반복 여부만 본다.
"""

import math
import re
from collections import Counter
from collections.abc import Sequence

from app.core.ingest.pdf import Page

EDGE_LINES = 2  # 쪽마다 앞·뒤 몇 줄을 머리글·꼬리말 후보로 볼지
MIN_KEY_CHARS = 4  # "}" 같은 짧은 반복 줄은 머리글로 보지 않는다
PAGE_NUMBER_RE = re.compile(r"^(?:-\s*)?\d{1,4}(?:\s*(?:/|of)\s*\d{1,4})?(?:\s*-)?$")
LEAD_DIGITS_RE = re.compile(r"^\d+")
TRAIL_DIGITS_RE = re.compile(r"\d+$")
def _key(line: str, page_number: int) -> str:
    """줄 앞뒤에 붙은 숫자가 그 쪽의 쪽번호일 때만 떼어 비교한다 ("2영진…"(2쪽), "…교수 3"(3쪽) → 같은 줄).

    "Chapter 12"처럼 쪽번호와 다른 숫자는 남겨서 번호만 다른 제목을 머리글로 오인하지 않는다.
    """
    number = str(page_number)
    key = line.strip()
    lead = LEAD_DIGITS_RE.match(key)
    if lead and lead.group(0) == number:  # 숫자 덩어리 전체가 쪽번호일 때만 ("12" ≠ "1")
        key = key[lead.end():]
    trail = TRAIL_DIGITS_RE.search(key)
    if trail and trail.group(0) == number:
        key = key[: trail.start()]
    return key.strip(" ,.")


def _edge_indexes(lines: list[str]) -> set[int]:
    filled = [i for i, line in enumerate(lines) if line.strip()]
    return set(filled[:EDGE_LINES]) | set(filled[-EDGE_LINES:])


def clean_pages(pages: Sequence[Page], *, min_ratio: float = 0.3, min_pages: int = 3) -> list[Page]:
    split = [page.text.splitlines() for page in pages]
    counts: Counter[str] = Counter()
    for page, lines in zip(pages, split, strict=True):
        counts.update({_key(lines[i], page.number) for i in _edge_indexes(lines)})
    threshold = max(min_pages, math.ceil(min_ratio * len(pages)))
    repeated = {k for k, c in counts.items() if len(k) >= MIN_KEY_CHARS and c >= threshold}

    cleaned = []
    for page, lines in zip(pages, split, strict=True):
        edges = _edge_indexes(lines)
        kept = [
            line for i, line in enumerate(lines)
            if not (i in edges and (_key(line, page.number) in repeated or PAGE_NUMBER_RE.match(line.strip())))
        ]
        cleaned.append(Page(page.number, "\n".join(kept).strip()))
    return cleaned
