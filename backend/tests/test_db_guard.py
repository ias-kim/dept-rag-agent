import pytest

from tests.db._guard import assert_safe_test_db


@pytest.mark.parametrize("name", ["dept_rag_test", "dept_rag_ci_test"])
def test_safe_names_allowed(name):
    assert_safe_test_db(name)


@pytest.mark.parametrize("name", ["dept_rag", "rag_test", "postgres", None])
def test_unsafe_names_rejected(name):
    with pytest.raises(pytest.fail.Exception, match="DROP 보호"):
        assert_safe_test_db(name)
