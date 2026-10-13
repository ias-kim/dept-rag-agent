from app.db.accounts import find_user, get_user, upsert_user, user_courses


def test_upsert_creates_user_with_courses(session):
    user = upsert_user(session, username="kim", password_hash="h", courses=frozenset({"AGENT", "AWS"}), daily_quota=30)
    assert find_user(session, "kim").id == user.id
    assert user_courses(session, user.id) == frozenset({"AGENT", "AWS"})
    assert get_user(session, user.id).daily_quota == 30


def test_upsert_replaces_courses_and_password(session):
    # 과목을 덧붙이지 않고 통째로 바꾼다 — 수강 취소한 과목의 전공 자료가 계속 보이면 권한 사고다
    user = upsert_user(session, username="kim", password_hash="old", courses=frozenset({"AGENT"}), daily_quota=50)
    again = upsert_user(session, username="kim", password_hash="new", courses=frozenset({"DB"}), daily_quota=10)
    assert again.id == user.id and again.password_hash == "new"
    assert user_courses(session, user.id) == frozenset({"DB"})


def test_guest_has_no_courses(session):
    user = upsert_user(session, username="guest", password_hash="h", courses=frozenset(), daily_quota=5)
    assert user_courses(session, user.id) == frozenset()


def test_unknown_user_is_none(session):
    assert find_user(session, "nobody") is None and get_user(session, 999) is None
