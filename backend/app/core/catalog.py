"""과목 카탈로그 — 과목 코드 → 이름·학년·학기.

학년은 DB 어디에도 없고 자료 파일명 접두어(2-1_ 등, data/MANIFEST.md)에만 있다. 화면이 2학년·3학년을 나눠 보이려면
여기 한 곳에 적어 둔다. 권한과는 무관하다 — 누가 어떤 과목을 볼 수 있는지는 enrollments 행만 정한다.
과목 폴더(data/major/<코드>)를 새로 만들면 여기 한 줄을 더한다. 빠뜨려도 화면은 코드만 보일 뿐 깨지지 않는다.
"""

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class CourseInfo:
    code: str
    name: str
    grade: int | None  # None = 카탈로그에 없는 과목. 화면은 "기타"로 묶는다
    semesters: tuple[str, ...]  # 자료 파일명 접두어와 같은 "학년-학기"


def _course(code: str, name: str, *semesters: str) -> CourseInfo:
    return CourseInfo(code, name, int(semesters[0].split("-")[0]), semesters)


CATALOG: dict[str, CourseInfo] = {c.code: c for c in (
    _course("AGENT", "AI 에이전트·MCP", "3-1", "3-2"),
    _course("AWS", "AWS 클라우드", "3-1"),
    _course("AI", "인공지능", "2-2"),
    _course("AUTODRIVE", "자율주행", "2-2"),
    _course("DB", "데이터베이스", "2-2"),
    _course("JS", "자바스크립트", "2-2"),
    _course("OOP", "객체지향 프로그래밍", "2-2"),
    _course("COMPUTING", "컴퓨터 활용", "2-1"),
    _course("DSA", "자료구조 및 알고리즘", "2-1"),
    _course("ML", "머신러닝", "2-1"),
    _course("WEB", "웹 프로그래밍", "2-1"),
)}


def course_info(code: str) -> CourseInfo:
    return CATALOG.get(code) or CourseInfo(code, code, None, ())


def sorted_by_grade(codes: Iterable[str]) -> list[CourseInfo]:
    """학년 높은 과목부터(재학생 대부분이 고학년 과목을 먼저 찾는다), 같은 학년은 코드순, 모르는 과목은 맨 뒤."""
    return sorted((course_info(c) for c in codes), key=lambda c: (c.grade is None, -(c.grade or 0), c.code))
