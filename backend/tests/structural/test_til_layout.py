"""TIL 파일 위치 규칙 검사 — til/{이름}/{YYYY-MM-DD}.md

허용 예외: til/_example.md, til/{이름}/README.md
"""

import re
from datetime import date
from pathlib import Path

TIL_DIR = Path(__file__).resolve().parents[3] / "til"
DATE_FILE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.md$")


def find_violations(til_dir: Path = TIL_DIR) -> list[str]:
    violations = []
    for path in sorted(p for p in til_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(til_dir)
        if path.name == ".DS_Store":
            continue
        if rel.parts == ("_example.md",):
            continue
        if len(rel.parts) != 2:
            violations.append(f"{rel}: til/{{이름}}/{{YYYY-MM-DD}}.md 형태가 아님")
            continue
        if rel.name == "README.md":
            continue
        m = DATE_FILE.match(rel.name)
        if not m:
            violations.append(f"{rel}: 파일명이 YYYY-MM-DD.md 가 아님")
            continue
        try:
            date(*map(int, m.groups()))
        except ValueError:
            violations.append(f"{rel}: 존재하지 않는 날짜")
    return violations


def test_til_layout():
    violations = find_violations()
    assert violations == [], "TIL 규칙 위반:\n" + "\n".join(violations)


def test_detector(tmp_path):
    (tmp_path / "홍길동").mkdir()
    (tmp_path / "홍길동" / "2026-09-20.md").write_text("ok")
    (tmp_path / "홍길동" / "README.md").write_text("ok")
    (tmp_path / "_example.md").write_text("ok")
    assert find_violations(tmp_path) == []

    (tmp_path / "홍길동" / "0920.md").write_text("bad")
    (tmp_path / "홍길동" / "2026-02-30.md").write_text("bad")
    (tmp_path / "loose.md").write_text("bad")
    assert len(find_violations(tmp_path)) == 3
