from datetime import date

from app.db.accounts import upsert_user
from app.db.usage import consume_quota, refund_quota, used_on

DAY = date(2026, 10, 1)


def make_user(session, quota=2):
    return upsert_user(session, username="kim", password_hash="h", courses=frozenset(), daily_quota=quota).id


def test_consume_stops_at_limit(session):
    uid = make_user(session)
    assert [consume_quota(session, uid, DAY, limit=2) for _ in range(3)] == [True, True, False]
    assert used_on(session, uid, DAY) == 2  # 거절된 호출은 세지 않는다


def test_zero_quota_never_consumes(session):
    # INSERT … ON CONFLICT의 WHERE는 첫 INSERT에 적용되지 않는다 — 0 한도가 1번 통과하면 안 된다
    uid = make_user(session, quota=0)
    assert consume_quota(session, uid, DAY, limit=0) is False
    assert used_on(session, uid, DAY) == 0


def test_days_are_counted_separately(session):
    uid = make_user(session, quota=1)
    assert consume_quota(session, uid, DAY, limit=1) is True
    assert consume_quota(session, uid, date(2026, 10, 2), limit=1) is True


def test_refund_gives_back_one_and_never_goes_negative(session):
    uid = make_user(session)
    consume_quota(session, uid, DAY, limit=2)
    refund_quota(session, uid, DAY)
    refund_quota(session, uid, DAY)
    assert used_on(session, uid, DAY) == 0


def test_concurrent_requests_cannot_exceed_limit(session, engine):
    # 읽고-비교하고-쓰면 동시 요청이 같은 값을 읽어 한도를 넘는다 — 한 문장 원자 증가로 막는다
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy.orm import Session

    uid = make_user(session, quota=1)
    session.commit()

    def attempt(_):
        with Session(engine) as s:
            ok = consume_quota(s, uid, DAY, limit=1)
            s.commit()
            return ok

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))
    assert results.count(True) == 1
