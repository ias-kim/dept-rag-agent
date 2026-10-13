"""API 의존성 — 세션, 인증 사용자, 답변 함수. 테스트는 app.dependency_overrides로 바꾼다."""

from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

import anthropic
import openai
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.api.throttle import LoginThrottle
from app.core.answer import Answer, make_llm
from app.core.config import Settings, get_settings
from app.core.embeddings import OpenAIEmbedder
from app.core.pipeline import PipelineDeps, UpstreamError, answer_question
from app.core.security import InvalidToken, decode_token, is_secret_configured
from app.db.accounts import get_user, user_courses
from app.db.session import make_engine
from app.mcp.server import UserContext

AnswerFn = Callable[[str, UserContext, Session], Awaitable[Answer]]
_bearer = HTTPBearer(auto_error=False)
UNAUTHORIZED = HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다", {"WWW-Authenticate": "Bearer"})
# 키가 비었을 때 로그인 결과(401/500)가 비밀번호 정답 여부에 따라 갈리지 않도록, 인증 전에 같은 503으로 멈춘다
AUTH_NOT_CONFIGURED = HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "로그인 서비스 설정이 완료되지 않았습니다")


def require_auth_configured(settings: Settings) -> None:
    if not is_secret_configured(settings.jwt_secret):
        raise AUTH_NOT_CONFIGURED


@dataclass(frozen=True)
class AuthedUser:
    user_id: int
    courses: frozenset[str]
    daily_quota: int


@lru_cache
def _engine() -> Engine:
    return make_engine()


def get_session() -> Iterator[Session]:
    with Session(_engine()) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def current_user(
    cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: SessionDep,
    settings: SettingsDep,
) -> AuthedUser:
    """토큰에서는 user_id만 꺼내고 과목·한도는 매 요청 DB에서 읽는다 — 수강 변경이 즉시 반영된다."""
    require_auth_configured(settings)
    if cred is None:
        raise UNAUTHORIZED
    try:
        user_id = decode_token(cred.credentials, secret=settings.jwt_secret)
    except InvalidToken:
        raise UNAUTHORIZED from None
    user = get_user(session, user_id)
    if user is None:  # 토큰 발급 뒤 삭제된 계정 — 남은 토큰으로 계속 질문하면 안 된다
        raise UNAUTHORIZED
    return AuthedUser(user.id, user_courses(session, user.id), user.daily_quota)


@lru_cache
def get_login_throttle() -> LoginThrottle:
    settings = get_settings()
    return LoginThrottle(max_per_account=settings.login_max_attempts_per_account,
                         max_per_ip=settings.login_max_attempts_per_ip,
                         window_seconds=settings.login_window_minutes * 60, max_keys=10_000)


def is_provider_outage(e: Exception) -> bool:
    """연결 실패·시간 초과·공급사 5xx·429만 장애로 본다. 4xx(잘못된 요청·인증)까지 한도를 되돌리면
    생성에서 400이 나는 질문을 한도 소모 없이 반복할 수 있다."""
    if isinstance(e, anthropic.APIConnectionError | openai.APIConnectionError):  # 시간 초과 포함
        return True
    if isinstance(e, anthropic.APIStatusError | openai.APIStatusError):
        return e.status_code >= 500 or e.status_code == 429
    return False


@lru_cache
def _clients() -> tuple[OpenAIEmbedder, anthropic.Anthropic]:
    # 공급사 클라이언트는 프로세스당 하나. Settings는 해시할 수 없어 인자로 받지 않고 프로세스 수명 동안 고정한다
    settings = get_settings()
    return OpenAIEmbedder.from_settings(settings), make_llm(settings)


def get_answer_fn(settings: SettingsDep) -> AnswerFn:
    embedder, llm = _clients()

    async def answer_fn(question: str, user: UserContext, session: Session) -> Answer:
        deps = PipelineDeps(session=session, embed_query=lambda q: embedder.embed([q])[0], llm=llm, settings=settings)
        try:
            return await answer_question(question, user, deps, mode=settings.router_mode)
        except (anthropic.APIError, openai.APIError) as e:
            if is_provider_outage(e):
                raise UpstreamError(type(e).__name__) from e
            raise

    return answer_fn
