"""계정 CLI — `make users ARGS="add kim --courses AGENT,AWS"`. 회원가입 API는 없다(설계 §4).

비밀번호는 getpass 또는 --password-stdin으로만 받는다. argv로 받으면 셸 기록·프로세스 목록에 남는다.
"""

import argparse
import getpass
import sys

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.accounts import upsert_user
from app.db.models import User
from app.db.session import make_engine

MIN_PASSWORD_CHARS = 8


def parse_courses(courses: str) -> frozenset[str]:
    """"agent, aws ," → {"AGENT", "AWS"}. DB는 대문자만 받으므로(CHECK) 여기서 맞춘다."""
    return frozenset(c.strip().upper() for c in courses.split(",") if c.strip())


def add_user(session: Session, username: str, password: str, *, courses: str, quota: int) -> User:
    if len(password) < MIN_PASSWORD_CHARS:
        raise ValueError(f"비밀번호는 {MIN_PASSWORD_CHARS}자 이상이어야 합니다")
    return upsert_user(session, username=username, password_hash=hash_password(password),
                       courses=parse_courses(courses), daily_quota=quota)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.core.users", allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add", help="계정 생성 또는 갱신(비밀번호·과목·한도 덮어씀)", allow_abbrev=False)
    add.add_argument("username")
    add.add_argument("--courses", default="", help="쉼표로 구분한 과목 코드. 비우면 게스트(학사만)")
    add.add_argument("--quota", type=int, default=None, help="일일 질문 한도 (기본: 설정값)")
    add.add_argument("--password-stdin", action="store_true", help="표준입력 첫 줄을 비밀번호로 사용")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    password = sys.stdin.readline().rstrip("\n") if args.password_stdin else getpass.getpass("비밀번호: ")
    quota = args.quota if args.quota is not None else get_settings().default_daily_quota
    courses = sorted(parse_courses(args.courses))
    with Session(make_engine()) as session:
        add_user(session, args.username, password, courses=args.courses, quota=quota)
        session.commit()
    # 세션이 닫힌 뒤 ORM 객체를 읽으면 만료된 속성을 다시 불러오다 실패하므로 입력값으로 출력한다
    print(f"계정 저장: {args.username} (과목 {courses or '없음'}, 일일 한도 {quota})")


if __name__ == "__main__":
    main()
