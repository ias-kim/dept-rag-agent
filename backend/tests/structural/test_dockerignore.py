"""이미지에 비밀값·원본 자료가 들어가지 않는지 — 이미지를 어디에 올리든 .env의 API 키가 따라가면 안 된다."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REQUIRED = [".env", "data", "eval/runs", "eval/grading", "**/node_modules", "docker/volumes", "**/.venv"]


def test_dockerignore_excludes_secrets_and_data():
    lines = {line.strip() for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()}
    missing = [p for p in REQUIRED if p not in lines]
    assert not missing, f".dockerignore에 빠짐: {missing}"


def test_dockerfile_never_copies_env():
    dockerfile = (ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY .env" not in dockerfile
    assert "COPY . " not in dockerfile  # 통째 복사는 .dockerignore 한 줄 실수로 비밀값까지 싣는다
