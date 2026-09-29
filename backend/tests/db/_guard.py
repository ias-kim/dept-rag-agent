import pytest


def assert_safe_test_db(name: str | None) -> None:
    """픽스처가 DROP DATABASE를 실행하므로 테스트 전용 이름만 허용한다."""
    if not name or not (name.startswith("dept_rag") and name.endswith("_test")):
        pytest.fail(f"TEST_DATABASE_URL은 dept_rag*_test DB만 허용 (DROP 보호): {name}")
