"""FastAPI 코드(SoT) → docs/generated/openapi.json (파생물).

결정론 보장: sort_keys, 고정 들여쓰기, 타임스탬프 없음.
사용: python scripts/gen_openapi.py [출력경로]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "docs" / "generated" / "openapi.json"


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
