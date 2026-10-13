"""HTTP 입출력 — 인증·한도·입력 검증·오류 변환만 한다. 답변은 주입된 answer_fn이 만든다.

순서: 입력 검증(422) → 한도 차감(429) → 답변. 검증 전에 차감하면 빈 질문에도 한도가 깎이고,
상류 장애(503)에서 되돌리지 않으면 학생이 서비스 장애로 하루 한도를 잃는다.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, StringConstraints

from app.api.deps import AnswerFn, AuthedUser, SessionDep, SettingsDep, current_user, get_answer_fn
from app.core.clock import seoul_today
from app.core.pipeline import UpstreamError
from app.core.security import issue_token, verify_password
from app.db.accounts import find_user
from app.db.usage import consume_quota, refund_quota
from app.mcp.server import UserContext

QUESTION_MAX_CHARS = 500
router = APIRouter(prefix="/api")


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AskRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=QUESTION_MAX_CHARS)]


class SourceOut(BaseModel):
    file: str
    page: int
    section: str | None


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceOut]
    intent: str | None
    notices: list[str]


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, session: SessionDep, settings: SettingsDep) -> TokenResponse:
    user = find_user(session, body.username)
    # 없는 계정과 틀린 비밀번호를 같은 문구·같은 검증 비용으로 처리해 계정 존재를 드러내지 않는다
    if not verify_password(body.password, user.password_hash if user else None):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "아이디 또는 비밀번호가 올바르지 않습니다")
    return TokenResponse(access_token=issue_token(user.id, secret=settings.jwt_secret, ttl_hours=settings.jwt_ttl_hours))


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest, user: Annotated[AuthedUser, Depends(current_user)], session: SessionDep,
              answer_fn: Annotated[AnswerFn, Depends(get_answer_fn)]) -> AskResponse:
    day = seoul_today()  # 서버는 UTC — 한국 자정에 한도가 초기화되도록 서울 날짜로 센다
    if not consume_quota(session, user.user_id, day, limit=user.daily_quota):
        session.rollback()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "오늘 질문 한도를 모두 사용했습니다")
    session.commit()  # 답변 전에 확정 — 답변 도중 실패해도 동시 요청이 한도를 넘지 못한다
    try:
        answer = await answer_fn(body.question, UserContext(user.user_id, user.courses), session)
    except UpstreamError:
        refund_quota(session, user.user_id, day)
        session.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "답변 서비스가 잠시 응답하지 않습니다") from None
    return AskResponse(answer=answer.text, sources=[SourceOut(file=s.file, page=s.page, section=s.section)
                                                    for s in answer.sources],
                       intent=answer.intent, notices=answer.notices)
