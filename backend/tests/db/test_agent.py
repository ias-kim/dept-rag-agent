import json
from datetime import date

import pytest

from app.core.agent import INVALID_TOOL_CALL, TOOL_ERROR_TEXT, TOOL_LIMIT_REACHED
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


def record_searches(monkeypatch, fail_first=False, fail_times=1):
    """MCP 서버 안의 실제 SQL 검색 호출을 기록한다. fail_first면 처음 fail_times번은 실제 DB 오류를 낸다 —
    잘못된 SQL로 트랜잭션을 중단 상태로 만들어, 되돌리지 않으면 이어지는 검색도 실패하게 한다."""
    from sqlalchemy import text

    from app.mcp import server

    real, calls = server.search_chunks, []

    def spy(*args, **kwargs):
        calls.append(kwargs["scope"])
        if fail_first and len(calls) <= fail_times:
            args[0].execute(text("SELECT 1/0"))  # 비밀번호=secret 같은 내부 문장이 오류에 실린다고 가정할 자리
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
    assert TOOL_LIMIT_REACHED in answer.notices and len(llm.calls) == 5  # 루프 4회 + 강제 생성 1회


@pytest.mark.anyio
async def test_agent_fourth_call_goes_straight_to_forced_generation(session):
    # 4회를 채운 뒤 도구 목록과 함께 모델을 또 부르면, 모델이 도구를 다시 요청할 때 그 호출이 통째로 버려진다
    seed_chunks(session, CORPUS)
    llm = FakeLLM(script=[tool_use_reply(*(academic_block(i) for i in range(4))), text_reply(f"답 [C{ACADEMIC_ID}]")])
    answer = await ask(session, llm)
    assert len(answer.tools_called) == 4 and TOOL_LIMIT_REACHED in answer.notices
    assert len(llm.calls) == 2 and "tools" not in llm.calls[1]


@pytest.mark.anyio
async def test_agent_partial_budget_in_one_response(session, monkeypatch):
    seed_chunks(session, CORPUS)
    searches = record_searches(monkeypatch)
    llm = FakeLLM(script=[tool_use_reply(*(academic_block(i) for i in range(3))),
                          tool_use_reply(academic_block(3), academic_block(4)), text_reply(f"답 [C{ACADEMIC_ID}]")])
    answer = await ask(session, llm)
    assert len(searches) == 4 and len(answer.tools_called) == 4
    # 두 번째 응답의 tool_use는 짝 맞는 tool_result 없이 다시 보내지 않는다(보내면 API 400) — 강제 생성은 새 대화다
    assert len(llm.calls) == 3 and "tools" not in llm.calls[2] and len(llm.calls[2]["messages"]) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("block", [
    ("t1", "search_major", {"query": "lec"}),  # 게스트에게 숨긴 도구
    ("t1", "search_academic", {"query": ["a"]}),  # 문자열이 아닌 query
    ("t1", "search_academic", {"query": "  "}),  # 빈 query
    ("t1", "search_academic", {"query": "가" * 501}),  # 질문 상한(500자)보다 긴 검색어 — 임베딩 4xx로 500이 난다
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
    session.commit()  # 운영처럼 자료는 확정돼 있다 — 실패 뒤 되돌리기가 시드까지 지우지 않게
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


@pytest.mark.anyio
async def test_agent_tool_error_text_is_not_forwarded_to_model(session, monkeypatch):
    from app.mcp import server

    def leak(*args, **kwargs):
        raise RuntimeError('relation "chunks" password=secret')

    seed_chunks(session, CORPUS)
    monkeypatch.setattr(server, "search_chunks", leak)
    llm = FakeLLM(script=[tool_use_reply(academic_block(1)), text_reply("제공된 자료에서 답을 찾을 수 없습니다.")])
    await ask(session, llm)
    result = llm.calls[1]["messages"][2]["content"][0]
    assert result["is_error"] is True and result["content"] == TOOL_ERROR_TEXT
    assert "secret" not in json.dumps(llm.calls[1]["messages"], ensure_ascii=False, default=str)


@pytest.mark.anyio
async def test_agent_db_error_is_rolled_back_so_retry_works(session, monkeypatch):
    seed_chunks(session, CORPUS)
    session.commit()
    record_searches(monkeypatch, fail_first=True, fail_times=2)
    llm = FakeLLM(script=[tool_use_reply(academic_block(1)), tool_use_reply(academic_block(2)),
                          tool_use_reply(academic_block(3)), text_reply(f"다시 찾은 답 [C{ACADEMIC_ID}]")])
    answer = await ask(session, llm)
    assert answer.citation_ok  # 세 번째 검색이 실제로 조각을 찾았다 = 중단된 트랜잭션이 되돌려졌다
    assert answer.notices.count("tool_error:search_academic") == 1  # 같은 도구 장애는 한 번만
    assert answer.tools_called == ["search_academic"] * 3  # 오류 난 호출도 실행한 호출이다
