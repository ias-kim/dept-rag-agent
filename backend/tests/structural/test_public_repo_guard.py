"""레포가 PUBLIC — 강의자료 원문이 섞이는 평가 산출물과 원본 PDF가 git에 올라가지 않아야 한다."""

from pathlib import Path

GITIGNORE = Path(__file__).resolve().parents[3] / ".gitignore"


def test_sensitive_outputs_are_gitignored():
    lines = {line.strip() for line in GITIGNORE.read_text(encoding="utf-8").splitlines()}
    assert {"/data/", "/eval/runs/", "/eval/grading/"} <= lines
