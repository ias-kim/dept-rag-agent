import json
from datetime import date

import pytest

from app.core.agent import INVALID_TOOL_CALL, TOOL_LIMIT_REACHED
from app.core.answer import EMPTY, REFUSED, Source
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


def record_searches(monkeypatch, fail_first=False):
    """MCP 서버 안의 실제 SQL 검색 호출을 기록한다. fail_first면 첫 호출에서 DB 장애를 흉내 낸다."""
    from app.mcp import server

    real, calls = server.search_chunks, []

    def spy(*args, **kwargs):
        calls.append(kwargs["scope"])
        if fail_first and len(calls) == 1:
            raise RuntimeError("db down")
        return real(*args, **kwargs)

    monkeypatch.setattr(server, "search_chunks", spy)
    return calls


def academic_block(i):
    return (f"t{i}", "search_academic", {"query": f"일정 {i}"})


@pytest.mark.anyio
async def test_agent_cap_counts_blocks_not_turns(session):
    seed_chunks(session, CORPUS)
    llm = FakeLLM(script=[tool_use_reply(*(academic_block(i) for i in range(5))), text_reply(f"모은 자료로 답 [C{ACADEMIC_ID}]")])
    answer = await ask(session, llm)
    assert answer.tools_called == ["search_academic"] * 4
    assert TOOL_LIMIT_REACHED in answer.notices
    assert len(llm.calls) == 2 and "tools" not in llm.calls[1]  # 두 번째는 도구 없는 강제 생성
    assert answer.citation_ok and answer.sources == [Source("academic/calendar.pdf", 1, None)]


@pytest.mark.anyio
async def test_agent_cap_across_turns(session, monkeypatch):
    seed_chunks(session, CORPUS)
    searches = record_searches(monkeypatch)
    llm = FakeLLM(script=[tool_use_reply(academic_block(i)) for i in range(5)] + [text_reply(f"답 [C{ACADEMIC_ID}]")])
    answer = await ask(session, llm)
    assert len(searches) == 4 and answer.tools_called == ["search_academic"] * 4
    assert TOOL_LIMIT_REACHED in answer.notices and len(llm.calls) == 6


@pytest.mark.anyio
async def test_agent_four_calls_then_answer_is_not_forced(session):
    seed_chunks(session, CORPUS)
    llm = FakeLLM(script=[tool_use_reply(*(academic_block(i) for i in range(4))), text_reply(f"답 [C{ACADEMIC_ID}]")])
    answer = await ask(session, llm)
    assert TOOL_LIMIT_REACHED not in answer.notices and len(answer.tools_called) == 4 and len(llm.calls) == 2


@pytest.mark.anyio
@pytest.mark.parametrize("block", [
    ("t1", "search_major", {"query": "lec"}),  # 게스트에게 숨긴 도구
    ("t1", "search_academic", {"query": ["a"]}),  # 문자열이 아닌 query
    ("t1", "search_academic", {"query": "  "}),  # 빈 query
])
async def test_agent_invalid_call_is_not_executed(session, monkeypatch, block):
    seed_chunks(session, CORPUS)
    searches = record_searches(monkeypatch)
    llm = FakeLLM(script=[tool_use_reply(block), text_reply("제공된 자료에서 답을 찾을 수 없습니다.")])
    answer = await ask(session, llm)
    assert searches == []
    assert INVALID_TOOL_CALL in answer.notices
    assert not any(n.startswith("tool_error:") for n in answer.notices)  # 모델 실수를 장애로 집계하지 않는다
    assert llm.calls[1]["messages"][2]["content"][0]["is_error"] is True


@pytest.mark.anyio
async def test_agent_tool_error_is_reported_and_loop_continues(session, monkeypatch):
    seed_chunks(session, CORPUS)
    record_searches(monkeypatch, fail_first=True)
    llm = FakeLLM(script=[
        tool_use_reply(academic_block(1)), tool_use_reply(academic_block(2)), text_reply(f"다시 찾은 답 [C{ACADEMIC_ID}]"),
    ])
    answer = await ask(session, llm)
    assert "tool_error:search_academic" in answer.notices
    assert llm.calls[1]["messages"][2]["content"][0]["is_error"] is True
    assert answer.text.startswith("다시 찾은 답") and answer.citation_ok


@pytest.mark.anyio
async def test_agent_embedding_failure_surfaces(session):
    seed_chunks(session, CORPUS)

    def down(q):
        raise RuntimeError("embedding down")

    llm = FakeLLM(script=[tool_use_reply(academic_block(1)), text_reply("자료가 없습니다")])
    with pytest.raises(RuntimeError, match="embedding down"):
        await ask(session, llm, embed=down)
    assert len(llm.calls) == 1  # 장애를 "자료 없음" 답으로 바꾸지 않고 바로 멈춘다


@pytest.mark.anyio
async def test_agent_direct_answer_without_tools(session):
    seed_chunks(session, CORPUS)
    declined = await ask(session, FakeLLM(script=[text_reply("제공된 자료에서 답을 찾을 수 없습니다.")]))
    assert declined.citation_ok and declined.sources == [] and declined.tools_called == []
    claimed = await ask(session, FakeLLM(script=[text_reply("스택은 LIFO 구조다.")]))
    assert "no_citation" in claimed.notices and not claimed.citation_ok


@pytest.mark.anyio
async def test_agent_refusal_and_truncation(session):
    seed_chunks(session, CORPUS)
    refused = await ask(session, FakeLLM(script=[text_reply("", stop_reason="refusal")]))
    assert refused.text == REFUSED and refused.notices == ["refused"]
    empty = await ask(session, FakeLLM(script=[text_reply("  ")]))
    assert empty.text == EMPTY and empty.notices == ["empty"]
    cut = await ask(session, FakeLLM(script=[text_reply("제공된 자료에서 답을 찾을 수 없습니다.", stop_reason="max_tokens")]))
    assert "truncated" in cut.notices
