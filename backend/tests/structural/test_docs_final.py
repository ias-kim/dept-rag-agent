"""마무리 문서가 실제 저장소와 어긋나지 않게 고정한다.

- 권한 설계 문서는 "이 테스트가 지킨다"고 적는다 → 적힌 테스트가 사라지거나 이름이 바뀌면 문서가 거짓이 된다.
- README 주요 화면은 그림 파일을 가리킨다 → 파일이 없으면 GitHub 첫 화면에 깨진 그림이 뜬다.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PERMISSIONS = ROOT / "docs" / "design" / "permissions.md"
README = ROOT / "README.md"


def defined_tests() -> set[str]:
    names = set()
    for path in (ROOT / "backend" / "tests").rglob("test_*.py"):
        names |= set(re.findall(r"^(?:async )?def (test_\w+)", path.read_text(encoding="utf-8"), re.MULTILINE))
    return names


def test_permissions_doc_cites_only_existing_tests():
    cited = set(re.findall(r"`(test_\w+)`", PERMISSIONS.read_text(encoding="utf-8")))
    assert cited, "권한 문서에서 테스트 인용을 찾지 못함"
    assert sorted(cited - defined_tests()) == []


def test_permissions_doc_is_final_edition():
    head = PERMISSIONS.read_text(encoding="utf-8").split("\n## ", 1)[0]
    assert "완성본" in head and "1판" not in head.splitlines()[0]
    assert "†" not in PERMISSIONS.read_text(encoding="utf-8")


def test_readme_screens_exist():
    text = README.read_text(encoding="utf-8")
    assert "## 주요 화면" in text
    section = text.split("## 주요 화면", 1)[1].split("\n## ", 1)[0]
    images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", section)
    assert len(images) >= 3
    assert [p for p in images if not (ROOT / p).is_file()] == []
