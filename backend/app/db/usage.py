"""일일 질문 한도 — 설계 §4.

한 문장(INSERT … ON CONFLICT … WHERE)으로 원자 증가한다. 읽고 비교한 뒤 쓰는 두 단계로 나누면
동시에 들어온 요청이 같은 값을 읽어 한도를 넘긴다.
"""

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

_CONSUME = text("""
INSERT INTO usage_daily (user_id, day, count) VALUES (:uid, :day, 1)
ON CONFLICT (user_id, day) DO UPDATE SET count = usage_daily.count + 1
WHERE usage_daily.count < :limit
RETURNING count
""")
_REFUND = text("UPDATE usage_daily SET count = GREATEST(count - 1, 0) WHERE user_id = :uid AND day = :day")
_USED = text("SELECT count FROM usage_daily WHERE user_id = :uid AND day = :day")


def consume_quota(session: Session, user_id: int, day: date, *, limit: int) -> bool:
    if limit <= 0:  # 첫 INSERT는 WHERE를 거치지 않으므로, 여기서 막지 않으면 0 한도 계정도 하루 1번 통과한다
        return False
    return session.execute(_CONSUME, {"uid": user_id, "day": day, "limit": limit}).scalar_one_or_none() is not None


def refund_quota(session: Session, user_id: int, day: date) -> None:
    session.execute(_REFUND, {"uid": user_id, "day": day})


def used_on(session: Session, user_id: int, day: date) -> int:
    return session.execute(_USED, {"uid": user_id, "day": day}).scalar_one_or_none() or 0
