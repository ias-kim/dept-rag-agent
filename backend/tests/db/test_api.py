import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_answer_fn, get_login_throttle, get_session
from app.api.throttle import LoginThrottle
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
        self.histories = []
        self.error = error

    async def __call__(self, question, user, session, history=()):
        self.calls.append((question, user))
        self.histories.append(history)
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
    throttle = LoginThrottle(max_per_account=5, max_per_ip=20, window_seconds=900, max_keys=1000)  # 테스트마다 새로 — 실패 기록이 다른 테스트로 새지 않게
    app.dependency_overrides[get_login_throttle] = lambda: throttle
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


def test_repeated_login_failures_are_throttled_per_ip_and_username(api, session):
    # 시도 제한이 없으면 비밀번호를 무한히 맞혀 볼 수 있다
    client, _ = api
    make_account(session)
    for _ in range(5):
        assert client.post("/api/auth/login", json={"username": "kim", "password": "nope-nope"}).status_code == 401
    blocked = client.post("/api/auth/login", json={"username": "kim", "password": "password123"})
    assert blocked.status_code == 429  # 맞는 비밀번호도 막혀야 추측이 의미 없어진다
    other = client.post("/api/auth/login", json={"username": "ghost", "password": "nope-nope"})
    assert other.status_code == 401


def test_successful_login_clears_failures(api, session):
    client, _ = api
    make_account(session)
    for _ in range(4):
        client.post("/api/auth/login", json={"username": "kim", "password": "nope-nope"})
    assert client.post("/api/auth/login", json={"username": "kim", "password": "password123"}).status_code == 200
    for _ in range(4):
        assert client.post("/api/auth/login", json={"username": "kim", "password": "nope-nope"}).status_code == 401


def test_missing_jwt_secret_does_not_reveal_password_correctness(api, session):
    # 키가 비었을 때 맞는 비밀번호만 500이 나면 비밀번호 정답 여부가 새어 나간다
    client, _ = api
    make_account(session)
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, jwt_secret="")
    right = client.post("/api/auth/login", json={"username": "kim", "password": "password123"})
    wrong = client.post("/api/auth/login", json={"username": "kim", "password": "nope-nope"})
    assert right.status_code == wrong.status_code == 503 and right.json() == wrong.json()
    assert client.post("/api/ask", json={"question": "q"}, headers={"Authorization": "Bearer x"}).status_code == 503


def test_login_input_length_is_limited(api, session):
    # 아주 긴 비밀번호는 argon2 해싱 부하로 서버를 붙잡는다
    client, _ = api
    assert client.post("/api/auth/login", json={"username": "k" * 65, "password": "p"}).status_code == 422
    assert client.post("/api/auth/login", json={"username": "kim", "password": "p" * 257}).status_code == 422


def test_me_returns_username_and_sorted_courses(api, session):
    client, _ = api
    user = make_account(session, courses=frozenset({"DB", "AGENT"}))
    res = client.get("/api/me", headers=auth(user.id))
    assert res.status_code == 200
    body = res.json()
    assert body["username"] == "kim" and body["courses"] == ["AGENT", "DB"]


def test_me_groups_course_details_by_grade(api, session):
    # 화면이 2학년·3학년 과목을 나눠 보이려면 학년이 있어야 한다. 학년이 높은 과목부터, 모르는 과목은 맨 뒤
    client, _ = api
    user = make_account(session, courses=frozenset({"DB", "AGENT", "NEW999"}))
    details = client.get("/api/me", headers=auth(user.id)).json()["course_details"]
    assert [(d["code"], d["grade"]) for d in details] == [("AGENT", 3), ("DB", 2), ("NEW999", None)]
    assert details[0]["name"] and details[0]["semesters"] == ["3-1", "3-2"]


def test_me_guest_has_no_courses(api, session):
    client, _ = api
    user = make_account(session, courses=frozenset())
    assert client.get("/api/me", headers=auth(user.id)).json()["courses"] == []


def test_me_requires_token(api, session):
    client, _ = api
    assert client.get("/api/me").status_code == 401


def test_me_does_not_consume_quota(api, session):
    client, fake = api
    user = make_account(session, quota=1)
    client.get("/api/me", headers=auth(user.id))
    assert used_on(session, user.id, seoul_today()) == 0 and fake.calls == []


def test_me_reflects_enrollment_change_without_relogin(api, session):
    # 화면 배지가 옛 수강 정보를 보여 주면 학생은 왜 전공 답이 안 나오는지 모른다 — 토큰이 아니라 DB에서 읽는다
    client, _ = api
    user = make_account(session, courses=frozenset({"AGENT"}))
    headers = auth(user.id)
    upsert_user(session, username="kim", password_hash=user.password_hash, courses=frozenset({"AWS"}), daily_quota=3)
    session.commit()
    assert client.get("/api/me", headers=headers).json()["courses"] == ["AWS"]


# ── 과목 선택·강의자료 목록 ──

def seed_documents(session):
    from tests.fakes import seed_chunks
    seed_chunks(session, [("major/AGENT/3-1_mcp.pdf", "major", "AGENT", 0),
                          ("major/AGENT/3-2_Docker.pdf", "major", "AGENT", 1),
                          ("major/WEB/2-1_VCS.pdf", "major", "WEB", 2),
                          ("academic/notices/a.md", "academic", None, 3)])
    session.commit()


def test_course_documents_lists_file_names_of_enrolled_course(api, session):
    client, fake = api
    user = make_account(session, courses=frozenset({"AGENT"}))
    seed_documents(session)
    res = client.get("/api/courses/AGENT/documents", headers=auth(user.id))
    assert res.status_code == 200
    assert res.json() == [{"file": "3-1_mcp.pdf", "pages": 1}, {"file": "3-2_Docker.pdf", "pages": 1}]
    assert used_on(session, user.id, seoul_today()) == 0 and fake.calls == []


def test_course_documents_of_other_or_unknown_course_are_forbidden_alike(api, session):
    # 남의 과목 자료 목록이 보이면 권한 겹을 화면 쪽에서 우회한다. 없는 과목과 같은 응답이라 존재 여부도 새지 않는다
    client, _ = api
    user = make_account(session, courses=frozenset({"AGENT"}))
    seed_documents(session)
    other = client.get("/api/courses/WEB/documents", headers=auth(user.id))
    unknown = client.get("/api/courses/NOPE/documents", headers=auth(user.id))
    assert other.status_code == unknown.status_code == 403
    assert other.json() == unknown.json()
    assert client.get("/api/courses/AGENT/documents").status_code == 401


def test_ask_with_course_narrows_search_scope_to_that_course(api, session):
    client, fake = api
    user = make_account(session, courses=frozenset({"AGENT", "DB"}))
    res = client.post("/api/ask", json={"question": "q", "course": "DB"}, headers=auth(user.id))
    assert res.status_code == 200
    assert fake.calls[0][1].courses == frozenset({"DB"})


def test_ask_with_course_not_enrolled_is_forbidden_without_using_quota(api, session):
    # 요청 본문의 과목으로 수강 범위를 넓힐 수 있으면 권한 겹 두 개가 모두 무의미해진다
    client, fake = api
    user = make_account(session, courses=frozenset({"AGENT"}))
    res = client.post("/api/ask", json={"question": "q", "course": "WEB"}, headers=auth(user.id))
    assert res.status_code == 403
    assert fake.calls == [] and used_on(session, user.id, seoul_today()) == 0


def test_ask_without_course_keeps_all_enrolled_courses(api, session):
    client, fake = api
    user = make_account(session, courses=frozenset({"AGENT", "DB"}))
    client.post("/api/ask", json={"question": "q", "course": None}, headers=auth(user.id))
    assert fake.calls[0][1].courses == frozenset({"AGENT", "DB"})


# ── 이어지는 대화 ──

def test_ask_passes_history_turns_to_answer_fn(api, session):
    client, fake = api
    user = make_account(session)
    history = [{"question": "MCP Host가 뭐야?", "answer": "Host는 앱입니다 [1]."}]
    res = client.post("/api/ask", json={"question": "원격이랑 로컬은?", "history": history}, headers=auth(user.id))
    assert res.status_code == 200
    (turn,) = fake.histories[0]
    assert (turn.question, turn.answer) == ("MCP Host가 뭐야?", "Host는 앱입니다 [1].")


def test_ask_without_history_sends_empty_history(api, session):
    client, fake = api
    user = make_account(session)
    client.post("/api/ask", json={"question": "q"}, headers=auth(user.id))
    assert tuple(fake.histories[0]) == ()


def test_history_size_is_limited_without_using_quota(api, session):
    # 상한이 없으면 아주 긴 이력으로 재작성 모델 입력(비용)을 무한히 키울 수 있다
    from app.api.routes import HISTORY_ANSWER_MAX_CHARS, HISTORY_MAX_TURNS
    client, fake = api
    user = make_account(session)
    too_many = [{"question": "q", "answer": "a"}] * (HISTORY_MAX_TURNS + 1)
    too_long = [{"question": "q", "answer": "가" * (HISTORY_ANSWER_MAX_CHARS + 1)}]
    for history in (too_many, too_long):
        res = client.post("/api/ask", json={"question": "q", "history": history}, headers=auth(user.id))
        assert res.status_code == 422
    assert fake.calls == [] and used_on(session, user.id, seoul_today()) == 0
