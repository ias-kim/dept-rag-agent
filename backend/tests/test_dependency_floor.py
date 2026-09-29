"""의존성 하한선 — 알려진 취약 버전으로 되돌아가지 않도록 막는다.

기준 근거: docs/exec-plans/(active|done)/2026-09-28-deps-upgrade.md
"""

import importlib
from importlib.metadata import version

import pytest
from packaging.version import Version

SECURITY_FLOOR = {
    "starlette": "0.47.2",  # CVE-2025-54121
}


@pytest.mark.parametrize("package, floor", SECURITY_FLOOR.items())
def test_security_floor(package, floor):
    assert Version(version(package)) >= Version(floor), f"{package}는 {floor} 이상이어야 함"


@pytest.mark.parametrize(
    "module",
    ["fastapi", "mcp", "anthropic", "openai", "sqlalchemy", "psycopg", "pgvector", "pydantic_settings"],
)
def test_core_libraries_import(module):
    importlib.import_module(module)
