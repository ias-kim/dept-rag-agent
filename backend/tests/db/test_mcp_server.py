import pytest

from app.mcp.connection import ToolError, connect, parse_hits
from app.mcp.server import TOOL_ACADEMIC, TOOL_MAJOR, UserContext, build_server
from tests.fakes import seed_chunks, unit

pytestmark = pytest.mark.anyio

CORPUS = [
    ("academic/calendar.pdf", "academic", None, 0),
    ("major/CS101/lec1.pdf", "major", "CS101", 0),
    ("major/CS202/lec1.pdf", "major", "CS202", 0),
]


def server_for(session, courses):
    user = UserContext(user_id=1, courses=frozenset(courses))
    return build_server(user, session, lambda q: unit(0), k=5, min_score=0.0)


async def tool_names(server):
    async with connect(server) as client:
        return sorted(t.name for t in (await client.list_tools()).tools)


async def call(server, name, arguments):
    async with connect(server) as client:
        return parse_hits(await client.call_tool(name, arguments))


async def test_no_enrollment_sees_only_academic(session):
    assert await tool_names(server_for(session, [])) == [TOOL_ACADEMIC]


async def test_enrolled_student_sees_both_tools(session):
    assert await tool_names(server_for(session, ["CS101"])) == [TOOL_ACADEMIC, TOOL_MAJOR]


async def test_search_major_returns_only_enrolled_course(session):
    seed_chunks(session, CORPUS)
    hits = await call(server_for(session, ["CS101"]), TOOL_MAJOR, {"query": "스택"})
    assert [h.source for h in hits] == ["major/CS101/lec1.pdf"]


async def test_course_code_argument_cannot_widen(session):
    seed_chunks(session, CORPUS)
    assert await call(server_for(session, ["CS101"]), TOOL_MAJOR, {"query": "스택", "course_code": "CS202"}) == []


async def test_course_code_argument_narrows_case_insensitively(session):
    seed_chunks(session, CORPUS)
    hits = await call(server_for(session, ["CS101", "CS202"]), TOOL_MAJOR, {"query": "스택", "course_code": "cs101"})
    assert [h.source for h in hits] == ["major/CS101/lec1.pdf"]


async def test_hidden_tool_call_is_rejected(session):
    seed_chunks(session, CORPUS)
    with pytest.raises(ToolError):
        await call(server_for(session, []), TOOL_MAJOR, {"query": "스택"})


async def test_academic_search_is_open(session):
    seed_chunks(session, CORPUS)
    hits = await call(server_for(session, []), TOOL_ACADEMIC, {"query": "수강신청"})
    assert [h.source for h in hits] == ["academic/calendar.pdf"]


async def test_empty_query_is_rejected(session):
    with pytest.raises(ToolError):
        await call(server_for(session, []), TOOL_ACADEMIC, {"query": "  "})
