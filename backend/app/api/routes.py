"""HTTP 입출력 — 인증·한도·입력 검증·오류 변환만 한다. 답변은 주입된 answer_fn이 만든다.

순서: 입력 검증(422) → 한도 차감(429) → 답변. 검증 전에 차감하면 빈 질문에도 한도가 깎이고,
상류 장애(503)에서 되돌리지 않으면 학생이 서비스 장애로 하루 한도를 잃는다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, StringConstraints

from app.api.deps import (
    AnswerFn,
    AuthedUser,
    SessionDep,
    SettingsDep,
    current_user,
    get_answer_fn,
    get_login_throttle,
    require_auth_configured,
)
from app.api.throttle import LoginThrottle
from app.core.catalog import sorted_by_grade
from app.core.clock import seoul_today
from app.core.conversation import RECENT_TURNS, Turn
from app.core.pipeline import UpstreamError
from app.core.security import issue_token, verify_password
from app.db.accounts import find_user
from app.db.documents import list_course_documents
from app.db.usage import consume_quota, refund_quota
from app.mcp.server import UserContext

QUESTION_MAX_CHARS = 500
# 이어지는 대화 상한. 화면(frontend/src/questions.js)이 같은 값으로 잘라 보낸다 — 서버만 줄이면 긴 대화의 질문이 통째로 422가 된다
HISTORY_MAX_TURNS = RECENT_TURNS
HISTORY_ANSWER_MAX_CHARS = 2000
COURSE_CODE_MAX_CHARS = 32  # DB 컬럼 VARCHAR(32)와 같다
# 수강 안 한 과목과 없는 과목에 같은 응답을 준다 — 다르면 어떤 과목 코드가 존재하는지 새어 나간다
NOT_ENROLLED = "수강 중인 과목만 선택할 수 있습니다"
router = APIRouter(prefix="/api")


USERNAME_MAX_CHARS = 64  # DB 컬럼 VARCHAR(64)와 같다
PASSWORD_MAX_CHARS = 256  # 상한이 없으면 아주 긴 비밀번호로 argon2 해싱 부하를 줄 수 있다


class LoginRequest(BaseModel):
    username: Annotated[str, StringConstraints(max_length=USERNAME_MAX_CHARS)]
    password: Annotated[str, StringConstraints(max_length=PASSWORD_MAX_CHARS)]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class HistoryTurn(BaseModel):
    question: Annotated[str, StringConstraints(max_length=QUESTION_MAX_CHARS)]
    answer: Annotated[str, StringConstraints(max_length=HISTORY_ANSWER_MAX_CHARS)]


class AskRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=QUESTION_MAX_CHARS)]
    # 고르면 그 과목 강의자료로만 좁힌다(학사 공지는 그대로). 넓히는 데는 쓸 수 없다 — ask()가 수강 과목과 대조한다
    course: Annotated[str, StringConstraints(max_length=COURSE_CODE_MAX_CHARS)] | None = None
    history: Annotated[list[HistoryTurn], Field(max_length=HISTORY_MAX_TURNS)] = []


class SourceOut(BaseModel):
    file: str
    page: int
    section: str | None


class CourseOut(BaseModel):
    code: str
    name: str
    grade: int | None
    semesters: list[str]


class MeResponse(BaseModel):
    username: str
    courses: list[str]
    course_details: list[CourseOut]  # 학년 높은 순. 화면이 학년별로 묶는다


class CourseDocumentOut(BaseModel):
    file: str
    pages: int


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceOut]
    intent: str | None
    notices: list[str]


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, session: SessionDep, settings: SettingsDep,
          throttle: Annotated[LoginThrottle, Depends(get_login_throttle)]) -> TokenResponse:
    require_auth_configured(settings)
    ip = request.client.host if request.client else ""
    if not throttle.try_acquire(ip, body.username):  # 맞는 비밀번호도 막아야 반복 추측이 의미 없어진다
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요")
    user = find_user(session, body.username)
    # 없는 계정과 틀린 비밀번호를 같은 문구·같은 검증 비용으로 처리해 계정 존재를 드러내지 않는다
    if not verify_password(body.password, user.password_hash if user else None):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "아이디 또는 비밀번호가 올바르지 않습니다")
    throttle.succeeded(ip, body.username)
    return TokenResponse(access_token=issue_token(user.id, secret=settings.jwt_secret, ttl_hours=settings.jwt_ttl_hours))


@router.get("/me", response_model=MeResponse)
def me(user: Annotated[AuthedUser, Depends(current_user)]) -> MeResponse:
    """화면 상단의 수강 과목 표시용. 과목은 current_user가 매 요청 DB에서 읽으므로 수강 변경이 바로 보인다.
    한도를 차감하지 않는다 — 화면을 열 때마다 부르는 요청이라 깎으면 질문도 안 했는데 한도가 줄어든다."""
    details = [CourseOut(code=c.code, name=c.name, grade=c.grade, semesters=list(c.semesters))
               for c in sorted_by_grade(user.courses)]
    return MeResponse(username=user.username, courses=sorted(user.courses), course_details=details)


@router.get("/courses/{code}/documents", response_model=list[CourseDocumentOut])
def course_documents(code: str, user: Annotated[AuthedUser, Depends(current_user)],
                     session: SessionDep) -> list[CourseDocumentOut]:
    """과목별 강의자료 목록. 한도를 차감하지 않는다(LLM을 부르지 않는 조회)."""
    if code not in user.courses:
        raise HTTPException(status.HTTP_403_FORBIDDEN, NOT_ENROLLED)
    docs = list_course_documents(session, code, allowed_courses=user.courses)
    return [CourseDocumentOut(file=d.file, pages=d.pages) for d in docs]


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest, user: Annotated[AuthedUser, Depends(current_user)], session: SessionDep,
              answer_fn: Annotated[AnswerFn, Depends(get_answer_fn)]) -> AskResponse:
    # 과목 선택은 좁히기만 한다. 한도 차감 전에 검사해야 잘못된 과목 요청이 한도를 깎지 않는다
    if body.course is not None and body.course not in user.courses:
        raise HTTPException(status.HTTP_403_FORBIDDEN, NOT_ENROLLED)
    courses = frozenset({body.course}) if body.course is not None else user.courses
    history = tuple(Turn(t.question, t.answer) for t in body.history)
    day = seoul_today()  # 서버는 UTC — 한국 자정에 한도가 초기화되도록 서울 날짜로 센다
    if not consume_quota(session, user.user_id, day, limit=user.daily_quota):
        session.rollback()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "오늘 질문 한도를 모두 사용했습니다")
    session.commit()  # 답변 전에 확정 — 답변 도중 실패해도 동시 요청이 한도를 넘지 못한다
    try:
        answer = await answer_fn(body.question, UserContext(user.user_id, courses), session, history)
    except UpstreamError:
        session.rollback()  # 도구 안의 DB 오류로 세션이 실패 상태면 되돌리기 자체가 실패해 500이 된다
        refund_quota(session, user.user_id, day)
        session.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "답변 서비스가 잠시 응답하지 않습니다") from None
    return AskResponse(answer=answer.text, sources=[SourceOut(file=s.file, page=s.page, section=s.section)
                                                    for s in answer.sources],
                       intent=answer.intent, notices=answer.notices)
