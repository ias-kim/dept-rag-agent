"""서비스 기준 날짜 — 서버(EC2)는 UTC라서, 그대로 쓰면 한국 오전 9시 전 질문의 '오늘'이 하루 밀린다."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

SEOUL = ZoneInfo("Asia/Seoul")


def seoul_today(now: datetime | None = None) -> date:
    return (now or datetime.now(SEOUL)).astimezone(SEOUL).date()
