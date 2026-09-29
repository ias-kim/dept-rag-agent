import pytest

from app.core.answer import NO_EVIDENCE
from app.core.config import Settings
from app.core.pipeline import PipelineDeps, answer_question, merge_hits
from app.mcp.server import UserContext
from tests.fakes import FakeLLM, make_hit, seed_chunks, unit

CORPUS = [
    ("academic/calendar.pdf", "academic", None, 0),
    ("major/CS101/lec1.pdf", "major", "CS101", 0),
    ("major/CS202/lec1.pdf", "major", "CS202", 0),
]


def deps(session, llm, axis=0, min_score=0.5):
    settings = Settings(_env_file=None, search_k=5, search_min_score=min_score)
    return PipelineDeps(session=session, embed_query=lambda q: unit(axis), llm=llm, settings=settings)


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
