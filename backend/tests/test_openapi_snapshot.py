"""API 계약 스냅샷 — SoT는 FastAPI 코드, docs/generated/openapi.json 은 파생물.

코드를 바꿨다면 `make generate` 후 스냅샷을 함께 커밋한다.
"""

import json
from pathlib import Path

from app.main import app

SNAPSHOT = Path(__file__).resolve().parents[2] / "docs" / "generated" / "openapi.json"


def test_openapi_snapshot_is_current():
    assert SNAPSHOT.exists(), "docs/generated/openapi.json 없음 → make generate"
    expected = json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    assert SNAPSHOT.read_text(encoding="utf-8") == expected, "스냅샷이 낡음 → make generate"
