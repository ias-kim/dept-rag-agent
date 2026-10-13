import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_answer_fn, get_session
from app.core.answer import Answer, Source
from app.core.clock import seoul_today
from app.core.config import Settings, get_settings
from app.core.pipeline import UpstreamError
from app.core.security import hash_password, issue_token
from app.db.accounts import upsert_user
from app.db.models import User
from app.db.usage import used_on
from app.main import app

SECRET = "t" * 32


class FakeAnswerFn:
    def __init__(self, error: Exception | None = None):
        self.calls = []
        self.error = error

    async def __call__(self, question, user, session):
        self.calls.append((question, user))
        if self.error:
            raise self.error
        return Answer(text="답[1]", sources=[Source("academic/a.md", 2, "제목")], citation_ok=True,
                      notices=[], intent="academic", intent_valid=True)


@pytest.fixture
def api(session):
    fake = FakeAnswerFn()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, jwt_secret=SECRET)
    app.dependency_overrides[get_answer_fn] = lambda: fake
    yield TestClient(app), fake
    app.dependency_overrides.clear()


def make_account(session, *, courses=frozenset({"AGENT"}), quota=3, password="password123"):
    user = upsert_user(session, username="kim", password_hash=hash_password(password), courses=courses,
                       daily_quota=quota)
    session.commit()
    return user


def auth(user_id):
    return {"Authorization": f"Bearer {issue_token(user_id, secret=SECRET, ttl_hours=1)}"}


def test_login_returns_token_that_opens_ask(api, session):
    client, fake = api
    make_account(session)
    res = client.post("/api/auth/login", json={"username": "kim", "password": "password123"})
    assert res.status_code == 200 and res.json()["token_type"] == "bearer"
    ask = client.post("/api/ask", json={"question": "  수강신청?  "},
                      headers={"Authorization": f"Bearer {res.json()['access_token']}"})
    assert ask.status_code == 200
    assert ask.json() == {"answer": "답[1]", "sources": [{"file": "academic/a.md", "page": 2, "section": "제목"}],
                          "intent": "academic", "notices": []}
    question, user = fake.calls[0]
    assert question == "수강신청?" and user.courses == frozenset({"AGENT"})


def test_login_failures_are_indistinguishable(api, session):
    client, _ = api
    make_account(session)
    wrong = client.post("/api/auth/login", json={"username": "kim", "password": "nope-nope"})
    unknown = client.post("/api/auth/login", json={"username": "ghost", "password": "nope-nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_ask_requires_valid_token(api, session):
    client, fake = api
    assert client.post("/api/ask", json={"question": "q"}).status_code == 401
    assert client.post("/api/ask", json={"question": "q"}, headers={"Authorization": "Bearer junk"}).status_code == 401
    assert fake.calls == []


def test_ask_rejects_token_of_deleted_user(api, session):
    client, _ = api
    user = make_account(session)
    headers = auth(user.id)
    session.delete(session.get(User, user.id))
    session.commit()
    assert client.post("/api/ask", json={"question": "q"}, headers=headers).status_code == 401


def test_invalid_question_does_not_consume_quota(api, session):
    client, fake = api
    user = make_account(session)
    for bad in ("   ", "가" * 501):
        assert client.post("/api/ask", json={"question": bad}, headers=auth(user.id)).status_code == 422
    assert used_on(session, user.id, seoul_today()) == 0 and fake.calls == []


def test_quota_exhausted_returns_429(api, session):
    client, fake = api
    user = make_account(session, quota=1)
    assert client.post("/api/ask", json={"question": "q"}, headers=auth(user.id)).status_code == 200
    assert client.post("/api/ask", json={"question": "q"}, headers=auth(user.id)).status_code == 429
    assert len(fake.calls) == 1


def test_upstream_error_refunds_quota(api, session):
    client, fake = api
    fake.error = UpstreamError("anthropic down")
    user = make_account(session)
    res = client.post("/api/ask", json={"question": "q"}, headers=auth(user.id))
    assert res.status_code == 503
    assert used_on(session, user.id, seoul_today()) == 0


def test_guest_courses_come_from_db_not_token(api, session):
    client, fake = api
    user = make_account(session, courses=frozenset())
    client.post("/api/ask", json={"question": "q"}, headers=auth(user.id))
    assert fake.calls[0][1].courses == frozenset()
