"""계정·수강 저장소 — 설계 §3·§4.

역할 컬럼은 없다. 전공 자료 접근은 enrollments 행이 있는지로만 판단하므로,
이 테이블이 곧 권한이다(행이 남아 있으면 그 과목 전공 자료가 보인다).
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Enrollment, User


def find_user(session: Session, username: str) -> User | None:
    return session.scalars(select(User).where(User.username == username)).one_or_none()


def get_user(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def user_courses(session: Session, user_id: int) -> frozenset[str]:
    return frozenset(session.scalars(select(Enrollment.course_code).where(Enrollment.user_id == user_id)))


def upsert_user(session: Session, *, username: str, password_hash: str, courses: frozenset[str],
                daily_quota: int) -> User:
    """계정을 만들거나 덮어쓴다. 수강 과목은 덧붙이지 않고 통째로 바꾼다 — 빠진 과목이 남으면 권한이 새어 나간다."""
    user = find_user(session, username)
    if user is None:
        user = User(username=username, password_hash=password_hash, daily_quota=daily_quota)
        session.add(user)
        session.flush()
    else:
        user.password_hash = password_hash
        user.daily_quota = daily_quota
    session.execute(delete(Enrollment).where(Enrollment.user_id == user.id))
    session.add_all(Enrollment(user_id=user.id, course_code=c) for c in sorted(courses))
    session.flush()
    return user
