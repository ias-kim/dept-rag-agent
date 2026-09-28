"""계층 의존 방향 검사 — 규칙 원문은 ARCHITECTURE.md.

api(3) → core(2) → mcp(1) → db(0). 자기보다 높은 계층을 import하면 실패.
예외: app.core.config 는 설정이라 어느 계층에서나 import 가능.
"""

import ast
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[2] / "app"

LAYER_RANK = {"db": 0, "mcp": 1, "core": 2, "api": 3}
ALLOWED_ANYWHERE = {"app.core.config"}


def layer_of(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) >= 2 and parts[0] == "app" and parts[1] in LAYER_RANK:
        return parts[1]
    return None


def imported_modules(path: Path, app_dir: Path = APP_DIR) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = ".".join(path.relative_to(app_dir.parent).with_suffix("").parts)
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # 상대 import → 절대 경로로 환산
                base = package.split(".")
                if path.name != "__init__.py":
                    base = base[:-1]
                base = base[: len(base) - (node.level - 1)]
                prefix = ".".join(base)
                mod = f"{prefix}.{node.module}" if node.module else prefix
            else:
                mod = node.module or ""
            modules.append(mod)
            modules.extend(f"{mod}.{alias.name}" for alias in node.names)
    return modules


def find_violations(app_dir: Path = APP_DIR) -> list[str]:
    violations = []
    for path in sorted(app_dir.rglob("*.py")):
        rel = ".".join(path.relative_to(app_dir.parent).with_suffix("").parts)
        src_layer = layer_of(rel)
        if src_layer is None:
            continue
        for mod in imported_modules(path, app_dir):
            if any(mod == a or mod.startswith(a + ".") for a in ALLOWED_ANYWHERE):
                continue
            dst_layer = layer_of(mod)
            if dst_layer and LAYER_RANK[dst_layer] > LAYER_RANK[src_layer]:
                violations.append(f"{rel} ({src_layer}) → {mod} ({dst_layer})")
    return sorted(set(violations))


def test_no_upward_imports():
    violations = find_violations()
    assert violations == [], "계층 역방향 import (ARCHITECTURE.md 참고):\n" + "\n".join(violations)


@pytest.mark.parametrize(
    "src, code, expect_violation",
    [
        ("db/bad.py", "from app.api import x\n", True),
        ("mcp/bad.py", "import app.core.router\n", True),
        ("db/ok.py", "from app.core.config import settings\n", False),
        ("api/ok.py", "from app.db import session\n", False),
        ("db/rel.py", "from ..mcp import tools\n", True),
    ],
)
def test_detector(tmp_path, src, code, expect_violation):
    app = tmp_path / "app"
    target = app / src
    target.parent.mkdir(parents=True)
    target.write_text(code, encoding="utf-8")
    assert bool(find_violations(app)) is expect_violation
