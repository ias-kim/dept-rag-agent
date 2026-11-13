from dataclasses import replace
from datetime import date

import pytest

from app.core.answer import NO_EVIDENCE
from app.core.config import Settings
from app.core.pipeline import (
    MAJOR_ONLY_TEXT,
    OUT_OF_SCOPE_TEXT,
    PipelineDeps,
    answer_question,
    merge_hits,
)
from app.mcp.connection import ToolError
from app.mcp.server import UserContext
from tests.fakes import FakeLLM, make_hit, seed_chunks, unit

CORPUS = [
    ("academic/calendar.pdf", "academic", None, 0),
    ("major/CS101/lec1.pdf", "major", "CS101", 0),
    ("major/CS202/lec1.pdf", "major", "CS202", 0),
]


def deps(session, llm, axis=0, min_score=0.5):
    settings = Settings(_env_file=None, search_k=5, search_min_score=min_score)
    return PipelineDeps(session=session, embed_query=lambda q: unit(axis), llm=llm, settings=settings,
                        today=lambda: date(2026, 9, 30))


def user(*courses):
    return UserContext(user_id=1, courses=frozenset(courses))


@pytest.mark.anyio
async def test_enrolled_student_gets_academic_and_own_course(session):
    seed_chunks(session, CORPUS)
    answer = await answer_question("스택이 뭐야?", user("CS101"), deps(session, FakeLLM("답")))
    assert sorted(h.source for h in answer.retrieved) == ["academic/calendar.pdf", "major/CS101/lec1.pdf"]


@pytest.mark.anyio
async def test_no_enrollment_never_retrieves_major(session):
    seed_chunks(session, CORPUS)
    answer = await answer_question("스택이 뭐야?", user(), deps(session, FakeLLM("답")))
    assert [h.source for h in answer.retrieved] == ["academic/calendar.pdf"]


@pytest.mark.anyio
async def test_no_hits_skips_llm(session):
    seed_chunks(session, CORPUS)
    llm = FakeLLM("무시됨")
    answer = await answer_question("관계없는 질문", user("CS101"), deps(session, llm, axis=5))
    assert answer.text == NO_EVIDENCE and llm.calls == []


@pytest.mark.anyio
async def test_prompt_contains_only_permitted_chunks(session):
    seed_chunks(session, CORPUS)
    llm = FakeLLM("답")
    await answer_question("스택?", user("CS101"), deps(session, llm))
    prompt = llm.calls[0]["messages"][0]["content"]
    assert "major/CS101/lec1.pdf" in prompt and "major/CS202" not in prompt


def test_merge_hits_dedupes_keeps_best_score_and_limits():
    hits = [make_hit(1, score=0.5), make_hit(2, score=0.9), make_hit(1, score=0.8), make_hit(3, score=0.7)]
    merged = merge_hits(hits, k=2)
    assert [(h.chunk_id, h.score) for h in merged] == [(2, 0.9), (1, 0.8)]


@pytest.mark.anyio
async def test_question_is_embedded_once_for_all_tools(session):
    seed_chunks(session, CORPUS)
    calls = []

    def embed(q):
        calls.append(q)
        return unit(0)

    d = deps(session, FakeLLM("답"))
    d = PipelineDeps(session=d.session, embed_query=embed, llm=d.llm, settings=d.settings)
    await answer_question("스택이 뭐야?", user("CS101"), d)  # 학사 + 전공 = 도구 2개
    assert calls == ["스택이 뭐야?"]


@pytest.mark.anyio
async def test_workflow_academic_intent_searches_only_academic(session):
    seed_chunks(session, CORPUS)
    llm = FakeLLM("답[C1].", classify_text="academic")
    answer = await answer_question("수강신청 언제?", user("CS101"), deps(session, llm), mode="workflow")
    assert [h.source for h in answer.retrieved] == ["academic/calendar.pdf"]
    assert (answer.intent, answer.intent_valid) == ("academic", True)


@pytest.mark.anyio
async def test_workflow_none_intent_answers_without_search_or_generation(session):
    seed_chunks(session, CORPUS)
    llm = FakeLLM("무시됨", classify_text="none")
    answer = await answer_question("학식 뭐야?", user("CS101"), deps(session, llm), mode="workflow")
    assert answer.text == OUT_OF_SCOPE_TEXT and answer.sources == [] and llm.calls == []
    assert answer.notices == ["out_of_scope"] and answer.intent == "none"


@pytest.mark.anyio
async def test_workflow_major_intent_for_guest_explains_restriction(session):
    seed_chunks(session, CORPUS)
    llm = FakeLLM("무시됨", classify_text="major")
    answer = await answer_question("스택?", user(), deps(session, llm), mode="workflow")
    assert answer.text == MAJOR_ONLY_TEXT and llm.calls == []
    assert answer.notices == ["major_requires_enrollment"]


@pytest.mark.anyio
async def test_workflow_invalid_label_uses_both_and_is_marked(session):
    seed_chunks(session, CORPUS)
    llm = FakeLLM("답[C1].", classify_text="모르겠음")
    answer = await answer_question("q", user("CS101"), deps(session, llm), mode="workflow")
    assert (answer.intent, answer.intent_valid) == ("both", False)
    assert sorted(h.source for h in answer.retrieved) == ["academic/calendar.pdf", "major/CS101/lec1.pdf"]


@pytest.mark.anyio
async def test_baseline_mode_does_not_classify(session):
    seed_chunks(session, CORPUS)
    llm = FakeLLM("답[C1].")
    answer = await answer_question("q", user("CS101"), deps(session, llm))
    assert llm.classify_calls == [] and answer.intent is None


@pytest.mark.anyio
async def test_one_failing_tool_does_not_sink_answer(session, monkeypatch):
    seed_chunks(session, CORPUS)
    from app.core import pipeline

    real = pipeline.parse_hits

    def flaky(result):
        hits = real(result)
        if hits and hits[0].scope == "major":
            raise ToolError("db down")
        return hits

    monkeypatch.setattr(pipeline, "parse_hits", flaky)
    answer = await answer_question("q", user("CS101"), deps(session, FakeLLM("답[C1].")))
    assert [h.source for h in answer.retrieved] == ["academic/calendar.pdf"]
    assert "tool_error:search_major" in answer.notices


@pytest.mark.anyio
async def test_blank_question_and_unknown_mode_are_rejected(session):
    with pytest.raises(ValueError):
        await answer_question("   ", user(), deps(session, FakeLLM()))
    with pytest.raises(ValueError):
        await answer_question("q", user(), deps(session, FakeLLM()), mode="planner")


def counting_deps(session, llm, calls):
    base = deps(session, llm)

    def embed(q):
        calls.append(q)
        return unit(0)

    return replace(base, embed_query=embed)


@pytest.mark.anyio
async def test_workflow_none_intent_skips_embedding_and_search(session):
    seed_chunks(session, CORPUS)
    calls = []
    answer = await answer_question("학식 뭐야?", user("CS101"), counting_deps(session, FakeLLM(classify_text="none"), calls),
                                   mode="workflow")
    assert calls == [] and answer.retrieved == []


@pytest.mark.anyio
async def test_workflow_both_intent_for_guest_searches_academic_only_and_explains(session):
    seed_chunks(session, CORPUS)
    llm = FakeLLM("답[C1].", classify_text="both")
    answer = await answer_question("그 수업 몇 교시고 뭐 배워?", user(), deps(session, llm), mode="workflow")
    assert [h.source for h in answer.retrieved] == ["academic/calendar.pdf"]
    assert "major_requires_enrollment" in answer.notices


@pytest.mark.anyio
async def test_planned_tool_outside_visible_list_is_never_called(session, monkeypatch):
    # 처리 표에 버그가 생겨 미수강자에게 search_major를 줘도, MCP 목록(권한 겹 ①)에 없으면 부르지 않는다
    seed_chunks(session, CORPUS)
    from app.core import pipeline
    from app.core.router import Plan
    from app.mcp.server import TOOL_ACADEMIC, TOOL_MAJOR

    monkeypatch.setattr(pipeline, "plan", lambda intent, u: Plan((TOOL_ACADEMIC, TOOL_MAJOR), ()))
    answer = await answer_question("q", user(), deps(session, FakeLLM("답[C1].", classify_text="major")), mode="workflow")
    assert [h.source for h in answer.retrieved] == ["academic/calendar.pdf"]
    assert not any(n.startswith("tool_error") for n in answer.notices)


@pytest.mark.anyio
async def test_pipeline_passes_today_to_generation(session):
    seed_chunks(session, CORPUS)
    llm = FakeLLM("답[C1].")
    await answer_question("q", user("CS101"), deps(session, llm))
    assert llm.calls[0]["messages"][0]["content"].startswith("오늘 날짜: 2026-09-30\n")


@pytest.mark.anyio
async def test_embedding_failure_surfaces_instead_of_becoming_no_evidence(session):
    # 임베딩이 MCP 도구 안에서 처음 실패하면 tool_error로 삼켜져 "자료 없음" 답이 나가고 한도만 깎인다
    seed_chunks(session, CORPUS)

    class ProviderDown(Exception):
        pass

    def broken_embed(q):
        raise ProviderDown("openai down")

    d = replace(deps(session, FakeLLM("답[C1].")), embed_query=broken_embed)
    with pytest.raises(ProviderDown):
        await answer_question("q", user("CS101"), d)


@pytest.mark.anyio
async def test_db_error_inside_tool_becomes_tool_error_not_500(session, monkeypatch):
    """MCP 2.2는 도구 안 예외를 isError가 아니라 MCPError로 던진다. 잡지 않으면 DB 오류 하나로 질문 전체가 500이 되고,
    agent 모드(같은 장애 → tool_error)와 평가에서 다르게 집계된다."""
    from sqlalchemy import text

    from app.mcp import server

    seed_chunks(session, CORPUS)
    session.commit()
    real = server.search_chunks

    def academic_db_error(*args, **kwargs):
        if kwargs["scope"] == "academic":
            args[0].execute(text("SELECT 1/0"))  # 트랜잭션 중단 — 되돌리지 않으면 이어지는 전공 검색도 실패한다
        return real(*args, **kwargs)

    monkeypatch.setattr(server, "search_chunks", academic_db_error)
    answer = await answer_question("q", user("CS101"), deps(session, FakeLLM("답[C2].")))
    assert "tool_error:search_academic" in answer.notices
    assert [h.source for h in answer.retrieved] == ["major/CS101/lec1.pdf"]


# ── 이어지는 대화: 이력이 있으면 질문을 독립 질문으로 다시 써서 분류·검색·생성에 쓴다 ──

FOLLOW_UP = "원격이랑 로컬은 뭐가 달라?"
STANDALONE = "MCP 원격 서버와 로컬 서버는 무엇이 다른가?"


def history():
    from app.core.conversation import Turn
    return (Turn("MCP에서 Host, Client, Server는 각각 무슨 역할이야?", "Host는 앱입니다 [1]."),)


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["baseline", "workflow"])
async def test_follow_up_is_searched_and_answered_as_standalone_question(session, mode):
    seed_chunks(session, CORPUS)
    embedded = []
    llm = FakeLLM("답 [C1]", classify_text="both", condense_text=STANDALONE)
    d = replace(deps(session, llm), embed_query=lambda q: embedded.append(q) or unit(0))
    await answer_question(FOLLOW_UP, user("CS101"), d, mode=mode, history=history())
    assert len(llm.condense_calls) == 1
    assert embedded and set(embedded) == {STANDALONE}  # 짧은 후속 질문 그대로 검색하면 근거가 안 잡힌다
    assert STANDALONE in llm.calls[-1]["messages"][0]["content"]
    if mode == "workflow":
        assert llm.classify_calls[0]["messages"][0]["content"] == STANDALONE


@pytest.mark.anyio
async def test_agent_receives_standalone_question(session):
    from tests.fakes import text_reply
    seed_chunks(session, CORPUS)
    llm = FakeLLM(script=[text_reply("제공된 자료에서 답을 찾을 수 없습니다.")], condense_text=STANDALONE)
    await answer_question(FOLLOW_UP, user("CS101"), deps(session, llm), mode="agent", history=history())
    assert STANDALONE in llm.calls[0]["messages"][0]["content"]


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["baseline", "workflow"])
async def test_no_history_means_no_rewrite_call(session, mode):
    # 이력이 없을 때 호출 수가 늘면 평가(단일 질문)의 비용·조건이 이전 실행과 달라진다
    seed_chunks(session, CORPUS)
    llm = FakeLLM("답", classify_text="both", condense_text=STANDALONE)
    await answer_question("스택이 뭐야?", user("CS101"), deps(session, llm), mode=mode)
    assert llm.condense_calls == []
