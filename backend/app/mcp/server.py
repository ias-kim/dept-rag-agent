"""권한 겹 1 — 요청마다 사용자 컨텍스트를 품은 MCP 서버를 만든다. 설계 §4, 결정 2.

사용자 역할·수강 과목은 UserContext로만 들어온다. LLM이 만드는 도구 인자로는 받지 않는다.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass

from mcp import types
from mcp.server.lowlevel import Server
from sqlalchemy.orm import Session

from app.db.search import search_chunks

TOOL_ACADEMIC = "search_academic"
TOOL_MAJOR = "search_major"

_QUERY = {"type": "string", "description": "검색할 질문 또는 핵심 키워드"}
ACADEMIC_SCHEMA = {"type": "object", "properties": {"query": _QUERY}, "required": ["query"]}
MAJOR_SCHEMA = {
    "type": "object",
    "properties": {
        "query": _QUERY,
        "course_code": {"type": "string", "description": "특정 과목으로 좁힐 때 과목 코드 (예: CS101)"},
    },
    "required": ["query"],
}


@dataclass(frozen=True)
class UserContext:
    user_id: int
    courses: frozenset[str]


def visible_tools(user: UserContext) -> list[types.Tool]:
    tools = [
        types.Tool(
            name=TOOL_ACADEMIC,
            description="학사 규정·학사일정·학과 공지를 검색한다. 수강신청, 성적, 졸업, 장학, 휴학, 일정 질문에 사용한다.",
            inputSchema=ACADEMIC_SCHEMA,
        )
    ]
    if user.courses:
        tools.append(
            types.Tool(
                name=TOOL_MAJOR,
                description="사용자가 수강 중인 전공 과목의 강의자료를 검색한다. 과목 개념, 예제, 과제, 시험 범위 질문에 사용한다.",
                inputSchema=MAJOR_SCHEMA,
            )
        )
    return tools


def _error(message: str) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=message)], isError=True)


def build_server(
    user: UserContext,
    session: Session,
    embed_query: Callable[[str], Sequence[float]],
    *,
    k: int,
    min_score: float,
) -> Server:
    async def list_tools(ctx, params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=visible_tools(user))

    async def call_tool(ctx, params) -> types.CallToolResult:
        args = params.arguments or {}
        query = str(args.get("query", "")).strip()
        if params.name == TOOL_ACADEMIC:
            scope, allowed = "academic", frozenset()
        elif params.name == TOOL_MAJOR and user.courses:
            scope = "major"
            requested = args.get("course_code")
            # 인자는 좁히기만 한다: 수강 과목과의 교집합
            allowed = user.courses & {str(requested).upper()} if requested else user.courses
        else:
            return _error(f"사용할 수 없는 도구입니다: {params.name}")
        if not query:
            return _error("query가 비어 있습니다")
        hits = search_chunks(session, embed_query(query), scope=scope, allowed_courses=allowed, k=k, min_score=min_score)
        payload = json.dumps([asdict(h) for h in hits], ensure_ascii=False)
        return types.CallToolResult(content=[types.TextContent(type="text", text=payload)])

    return Server("dept-rag", on_list_tools=list_tools, on_call_tool=call_tool)
