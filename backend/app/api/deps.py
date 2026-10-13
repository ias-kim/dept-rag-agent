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

from app.core.answer import Answer, make_llm
from app.core.config import Settings, get_settings
from app.core.embeddings import OpenAIEmbedder
from app.core.pipeline import PipelineDeps, UpstreamError, answer_question
from app.core.security import InvalidToken, decode_token
from app.db.accounts import get_user, user_courses
from app.db.session import make_engine
from app.mcp.server import UserContext

AnswerFn = Callable[[str, UserContext, Session], Awaitable[Answer]]
_bearer = HTTPBearer(auto_error=False)
UNAUTHORIZED = HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다", {"WWW-Authenticate": "Bearer"})


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
            raise UpstreamError(type(e).__name__) from e

    return answer_fn
