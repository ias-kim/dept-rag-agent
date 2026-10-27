import json
from datetime import date

import pytest

from app.core.answer import Source
from app.core.config import Settings
from app.core.pipeline import PipelineDeps, answer_question
from app.mcp.server import UserContext
from tests.fakes import FakeLLM, seed_chunks, text_reply, tool_use_reply, unit

# seed 순서대로 chunk_id 1·2·3 (테스트마다 TRUNCATE … RESTART IDENTITY)
CORPUS = [
    ("academic/calendar.pdf", "academic", None, 0),
    ("major/CS101/lec1.pdf", "major", "CS101", 0),
    ("major/CS202/lec1.pdf", "major", "CS202", 0),
]
ACADEMIC_ID, CS101_ID = 1, 2


def deps(session, llm, *, search_k=5, embed=None, **overrides):
    settings = Settings(_env_file=None, search_k=search_k, search_min_score=0.5, **overrides)
    return PipelineDeps(session=session, embed_query=embed or (lambda q: unit(0)), llm=llm, settings=settings,
                        today=lambda: date(2026, 9, 30))


def user(*courses):
    return UserContext(user_id=1, courses=frozenset(courses))


async def ask(session, llm, *courses, **kw):
    return await answer_question("스택이 뭐야?", user(*courses), deps(session, llm, **kw), mode="agent")


def tool_names(call):
    return sorted(t["name"] for t in call["tools"])


@pytest.mark.anyio
async def test_agent_guest_gets_only_academic_tool(session):
    seed_chunks(session, CORPUS)
    guest, student = FakeLLM(script=[text_reply("답")]), FakeLLM(script=[text_reply("답")])
    await ask(session, guest)
    await ask(session, student, "CS101")
    assert tool_names(guest.calls[0]) == ["search_academic"]
    assert tool_names(student.calls[0]) == ["search_academic", "search_major"]
    assert all("input_schema" in t for t in student.calls[0]["tools"])


@pytest.mark.anyio
async def test_agent_runs_tool_and_answers_with_citation(session):
    seed_chunks(session, CORPUS)
    llm = FakeLLM(script=[tool_use_reply(("t1", "search_major", {"query": "lec"})), text_reply(f"스택은 LIFO다 [C{CS101_ID}]")])
    answer = await ask(session, llm, "CS101")
    assert answer.sources == [Source("major/CS101/lec1.pdf", 1, None)]
    assert answer.citation_ok
    assert answer.tools_called == ["search_major"]
    assert answer.intent is None


@pytest.mark.anyio
async def test_agent_feeds_tool_result_and_preserves_thinking(session):
    seed_chunks(session, CORPUS)
    first = tool_use_reply(("t1", "search_major", {"query": "lec"}))
    llm = FakeLLM(script=[first, text_reply(f"답 [C{CS101_ID}]")])
    await ask(session, llm, "CS101")
    messages = llm.calls[1]["messages"]
    assert messages[1] == {"role": "assistant", "content": first.content}
    assert messages[1]["content"][0].type == "thinking"  # 빼면 실제 API가 400
    result = messages[2]["content"][0]
    assert messages[2]["role"] == "user" and result["type"] == "tool_result" and result["tool_use_id"] == "t1"
    assert f"[C{CS101_ID}]" in result["content"] and "major/CS101/lec1.pdf p.1" in result["content"]


@pytest.mark.anyio
async def test_agent_citation_from_earlier_call_is_valid(session):
    seed_chunks(session, CORPUS)
    llm = FakeLLM(script=[
        tool_use_reply(("t1", "search_academic", {"query": "일정"})),
        tool_use_reply(("t2", "search_major", {"query": "lec"})),
        text_reply(f"학사 일정은 이렇다 [C{ACADEMIC_ID}]"),
    ])
    answer = await ask(session, llm, "CS101", search_k=1)
    assert answer.citation_ok and "invalid_citation" not in answer.notices
    assert sorted(h.source for h in answer.retrieved) == ["academic/calendar.pdf", "major/CS101/lec1.pdf"]


@pytest.mark.anyio
async def test_agent_first_message_has_today_and_no_courses(session):
    seed_chunks(session, CORPUS)
    llm = FakeLLM(script=[text_reply("답")])
    await ask(session, llm, "CS101")
    first = llm.calls[0]
    assert first["messages"][0]["content"].startswith("오늘 날짜: 2026-09-30")
    assert "CS101" not in first["system"] + json.dumps(first["messages"], ensure_ascii=False)
