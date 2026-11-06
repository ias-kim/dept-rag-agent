"""권한 행렬 재검증 (6주차) — 모드 3종 × 역할 2종에서 남의 과목 전공 조각이 검색 결과·모델 입력에 닿지 않는다.

조각은 모두 같은 축이라 점수로는 걸러지지 않는다. 막는 것은 권한 겹(MCP 도구 노출·인자 좁히기, SQL 조건)뿐이다.
역할 정의와 행렬 전체: docs/design/permissions.md
"""

import json
from datetime import date

import pytest

from app.core.config import Settings
from app.core.pipeline import MODES, PipelineDeps, answer_question
from app.mcp.server import UserContext
from tests.fakes import FakeLLM, seed_chunks, text_reply, tool_use_reply, unit

CORPUS = [
    ("academic/calendar.pdf", "academic", None, 0),
    ("major/CS101/lec1.pdf", "major", "CS101", 0),
    ("major/CS202/lec1.pdf", "major", "CS202", 0),
]
GUEST, CS101_STUDENT = frozenset(), frozenset({"CS101"})


def llm_for(mode: str) -> FakeLLM:
    if mode == "agent":  # 모델이 보이든 말든 전공 도구를 부르고, 남의 과목으로 넓히려 시도한다
        return FakeLLM(script=[
            tool_use_reply(("t1", "search_academic", {"query": "일정"}),
                           ("t2", "search_major", {"query": "lec", "course_code": "CS202"}),
                           ("t3", "search_major", {"query": "lec"})),
            text_reply("제공된 자료에서 답을 찾을 수 없습니다."),
        ])
    return FakeLLM("제공된 자료에서 답을 찾을 수 없습니다.", classify_text="both")


async def ask(session, mode, courses, llm):
    deps = PipelineDeps(session=session, embed_query=lambda q: unit(0), llm=llm,
                        settings=Settings(_env_file=None, search_k=5, search_min_score=0.5),
                        today=lambda: date(2026, 9, 30))
    return await answer_question("스택이 뭐야?", UserContext(user_id=1, courses=courses), deps, mode=mode)


def model_inputs(llm: FakeLLM) -> str:
    return json.dumps([(c.get("system"), c.get("messages")) for c in llm.calls], ensure_ascii=False, default=str)


@pytest.mark.anyio
@pytest.mark.parametrize("courses", [GUEST, CS101_STUDENT], ids=["guest", "cs101"])
@pytest.mark.parametrize("mode", MODES)
async def test_no_foreign_major_chunk_reaches_answer_or_model(session, mode, courses):
    seed_chunks(session, CORPUS)
    llm = llm_for(mode)
    answer = await ask(session, mode, courses, llm)
    majors = {h.course_code for h in answer.retrieved if h.scope == "major"}
    assert majors <= courses
    assert "major/CS202" not in model_inputs(llm)
    if not courses:
        assert "major/" not in model_inputs(llm)


@pytest.mark.anyio
@pytest.mark.parametrize(("courses", "expected"), [
    (GUEST, {"search_academic"}),
    (CS101_STUDENT, {"search_academic", "search_major"}),
], ids=["guest", "cs101"])
async def test_agent_tools_argument_matches_mcp_visibility(session, courses, expected):
    # 기대값을 visible_tools에서 가져오면 노출 필터가 망가질 때 기대값도 같이 망가져 통과한다 — 고정값으로 둔다
    seed_chunks(session, CORPUS)
    llm = FakeLLM(script=[text_reply("답")])
    await ask(session, "agent", courses, llm)
    assert {t["name"] for t in llm.calls[0]["tools"]} == expected
