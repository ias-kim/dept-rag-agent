"""통합 테스트 (6주차) — 로그인 → /api/ask → 실제 파이프라인(agent)·MCP·DB → 응답 출처.

test_api.py는 답변 함수를 가짜로 바꿔 HTTP 규칙만 본다. 여기서는 공급사 클라이언트(LLM·임베딩)만 가짜로 두고
실제 get_answer_fn(ROUTER_MODE=agent)을 지나므로, 운영 배선이 바뀌어 agent 경로가 끊기면 여기서 드러난다.
"""

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

from app.api import deps as api_deps
from app.api.deps import get_login_throttle, get_session
from app.api.throttle import LoginThrottle
from app.core.clock import seoul_today
from app.core.config import Settings, get_settings
from app.core.security import hash_password
from app.db.accounts import upsert_user
from app.db.usage import used_on
from app.main import app
from tests.fakes import FakeLLM, seed_chunks, text_reply, tool_use_reply, unit

SECRET = "t" * 32
PASSWORD = "password123"
CORPUS = [
    ("academic/calendar.pdf", "academic", None, 0),
    ("major/CS101/lec1.pdf", "major", "CS101", 0),
]
CS101_ID = 2


class AxisEmbedder:
    """모든 질문을 축 0으로 — 시드 조각과 같은 축이라 권한만이 결과를 거른다."""

    def __init__(self, error: Exception | None = None):
        self.error = error

    def embed(self, texts):
        if self.error:
            raise self.error
        return [unit(0) for _ in texts]


@pytest.fixture
def wire(session, monkeypatch):
    """실제 get_answer_fn에 가짜 공급사 클라이언트를 꽂는다. wire(llm, embedder) → TestClient."""
    seed_chunks(session, CORPUS)
    settings = Settings(_env_file=None, jwt_secret=SECRET, router_mode="agent", search_min_score=0.5)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: settings
    throttle = LoginThrottle(max_per_account=5, max_per_ip=20, window_seconds=900, max_keys=1000)
    app.dependency_overrides[get_login_throttle] = lambda: throttle

    def connect(llm, embedder=None):
        monkeypatch.setattr(api_deps, "_clients", lambda: (embedder or AxisEmbedder(), llm))
        return TestClient(app)

    yield connect
    app.dependency_overrides.clear()


def login(client, session, username, courses):
    user = upsert_user(session, username=username, password_hash=hash_password(PASSWORD), courses=courses,
                       daily_quota=3)
    session.commit()
    res = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert res.status_code == 200
    return user, {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_login_ask_returns_sources_from_seeded_chunk(wire, session):
    llm = FakeLLM(script=[
        tool_use_reply(("t1", "search_academic", {"query": "일정"})),
        tool_use_reply(("t2", "search_major", {"query": "스택"})),
        text_reply(f"스택은 나중에 넣은 것을 먼저 꺼낸다 [C{CS101_ID}]"),
    ])
    client = wire(llm)
    user, headers = login(client, session, "kim", frozenset({"CS101"}))
    res = client.post("/api/ask", json={"question": "스택이 뭐야?"}, headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["sources"] == [{"file": "major/CS101/lec1.pdf", "page": 1, "section": None}]
    assert "[1]" in body["answer"] and body["intent"] is None and body["notices"] == []
    assert used_on(session, user.id, seoul_today()) == 1  # 도구를 두 번 불러도 한도는 질문 1회


def test_guest_login_ask_never_sees_major(wire, session):
    llm = FakeLLM(script=[tool_use_reply(("t1", "search_major", {"query": "스택"})),
                          text_reply("제공된 자료에서 답을 찾을 수 없습니다.")])
    client = wire(llm)
    _, headers = login(client, session, "guest", frozenset())
    res = client.post("/api/ask", json={"question": "스택이 뭐야?"}, headers=headers)
    assert res.status_code == 200
    assert not any(s["file"].startswith("major/") for s in res.json()["sources"])
    assert [t["name"] for t in llm.calls[0]["tools"]] == ["search_academic"]


def test_agent_embedding_outage_returns_503_and_refunds(wire, session):
    outage = openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1/embeddings"))
    llm = FakeLLM(script=[tool_use_reply(("t1", "search_academic", {"query": "일정"})), text_reply("자료 없음")])
    client = wire(llm, AxisEmbedder(error=outage))
    user, headers = login(client, session, "kim", frozenset({"CS101"}))
    res = client.post("/api/ask", json={"question": "수강신청 언제야?"}, headers=headers)
    assert res.status_code == 503
    assert used_on(session, user.id, seoul_today()) == 0
