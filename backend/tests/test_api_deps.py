import anthropic
import httpx
import openai
import pytest

from app.api import deps
from app.core.config import Settings
from app.core.pipeline import UpstreamError

REQ = httpx.Request("POST", "https://provider.example")


def status_error(cls, code):
    return cls("boom", response=httpx.Response(code, request=REQ), body=None)


@pytest.fixture
def answer_fn(monkeypatch):
    monkeypatch.setattr(deps, "_clients", lambda: (None, None))  # 실제 공급사 클라이언트를 만들지 않는다
    raised = {}

    async def fake_answer_question(*args, **kwargs):
        raise raised["error"]

    monkeypatch.setattr(deps, "answer_question", fake_answer_question)
    fn = deps.get_answer_fn(Settings(_env_file=None))

    async def call(error):
        raised["error"] = error
        return await fn("q", None, None)

    return call


@pytest.mark.anyio
@pytest.mark.parametrize("error", [
    anthropic.APIConnectionError(request=REQ),
    openai.APIConnectionError(request=REQ),
    status_error(anthropic.InternalServerError, 500),
    status_error(openai.InternalServerError, 503),
    status_error(anthropic.RateLimitError, 429),
])
async def test_provider_outage_becomes_upstream_error(answer_fn, error):
    with pytest.raises(UpstreamError):
        await answer_fn(error)


@pytest.mark.anyio
@pytest.mark.parametrize("error", [
    status_error(anthropic.BadRequestError, 400),
    status_error(openai.AuthenticationError, 401),
])
async def test_provider_client_error_is_not_treated_as_outage(answer_fn, error):
    # 공급사 4xx까지 되돌리면 생성에서 400이 나는 질문을 한도 소모 없이 반복할 수 있다
    with pytest.raises(type(error)):
        await answer_fn(error)
