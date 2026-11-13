from app.core.catalog import CATALOG, course_info, sorted_by_grade


def test_known_course_has_korean_name_grade_and_semesters():
    agent = course_info("AGENT")
    assert agent.code == "AGENT" and agent.grade == 3 and agent.semesters == ("3-1", "3-2")
    assert agent.name != "AGENT"


def test_grade_matches_semester_prefix_for_every_course():
    # 학년 숫자와 학기 접두어(자료 파일명 2-1_ 등)가 어긋나면 과목이 엉뚱한 학년 아래에 보인다
    for info in CATALOG.values():
        assert info.semesters and all(s.startswith(f"{info.grade}-") for s in info.semesters), info.code


def test_unknown_code_falls_back_to_code_without_grade():
    # 카탈로그에 안 넣은 과목을 수강 등록해도 화면이 깨지지 않고 코드로라도 보여야 한다
    info = course_info("NEW999")
    assert info.code == info.name == "NEW999" and info.grade is None and info.semesters == ()


def test_sorted_by_grade_puts_higher_grade_first_and_unknown_last():
    codes = [c.code for c in sorted_by_grade(["DB", "NEW999", "AGENT", "AWS"])]
    assert codes == ["AGENT", "AWS", "DB", "NEW999"]
