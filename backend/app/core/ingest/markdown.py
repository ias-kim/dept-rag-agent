"""텍스트 자료(.md) — 시간표·공지처럼 직접 붙여 넣은 학사 정보. `## 제목`마다 한 쪽으로 나눈다.

쪽 첫 줄이 제목이 되므로 structure 분할에서 그대로 섹션 라벨이 된다. PDF가 아니므로 머리글 정리는 하지 않는다.
"""

import re
from pathlib import Path

from app.core.ingest.pdf import Page

H2_RE = re.compile(r"^##(?!#)\s*", re.MULTILINE)
HEADING_MARK_RE = re.compile(r"^#+\s*", re.MULTILINE)


def extract_markdown(path: Path) -> list[Page]:
    text = path.read_text(encoding="utf-8")
    sections = [HEADING_MARK_RE.sub("", s).strip() for s in H2_RE.split(text)]
    return [Page(i, s) for i, s in enumerate((s for s in sections if s), start=1)]
