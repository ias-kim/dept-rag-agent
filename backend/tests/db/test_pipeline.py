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
        await answer_question("q", user(), deps(session, FakeLLM()), mode="agent")
