import pytest

from app.core.security import verify_password
from app.core.users import add_user, build_parser
from app.db.accounts import user_courses


def test_add_user_normalizes_courses_and_hashes_password(session):
    user = add_user(session, "kim", "password123", courses="agent, aws ,", quota=20)
    assert user_courses(session, user.id) == frozenset({"AGENT", "AWS"})
    assert verify_password("password123", user.password_hash)


def test_short_password_is_rejected(session):
    with pytest.raises(ValueError, match="8자"):
        add_user(session, "kim", "short", courses="", quota=5)


def test_password_cannot_be_passed_as_argument():
    # argv의 비밀번호는 셸 기록·프로세스 목록에 남는다
    with pytest.raises(SystemExit):
        build_parser().parse_args(["add", "kim", "--password", "secret123"])


def test_password_option_prefix_is_not_accepted_as_abbreviation():
    # argparse 기본 약어 허용 때문에 --password가 --password-stdin으로 해석되면 사용자가 착각한다
    with pytest.raises(SystemExit):
        build_parser().parse_args(["add", "kim", "--password"])
