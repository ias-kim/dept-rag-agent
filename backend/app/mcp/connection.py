"""같은 프로세스 메모리 전송으로 MCP 서버에 붙는 클라이언트 (스파이크 S1에서 확인한 형태)."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio
from mcp import ClientSession, types
from mcp.server.lowlevel import Server
from mcp.shared.memory import create_client_server_memory_streams

from app.db.search import ChunkHit


class ToolError(RuntimeError):
    """MCP 도구가 isError 결과를 돌려줌."""


@asynccontextmanager
async def connect(server: Server) -> AsyncIterator[ClientSession]:
    try:
        async with create_client_server_memory_streams() as (client_streams, server_streams), anyio.create_task_group() as tg:
            tg.start_soon(server.run, server_streams[0], server_streams[1], server.create_initialization_options())
            async with ClientSession(*client_streams) as client:
                await client.initialize()
                yield client
            tg.cancel_scope.cancel()
    except BaseExceptionGroup as group:
        # anyio 태스크 그룹(중첩 포함)이 본문 예외(ToolError 등)를 그룹으로 감싸므로 하나뿐이면 풀어서 던진다
        inner: BaseException = group
        while isinstance(inner, BaseExceptionGroup) and len(inner.exceptions) == 1:
            inner = inner.exceptions[0]
        if inner is group:
            raise
        raise inner from None


def parse_hits(result: types.CallToolResult) -> list[ChunkHit]:
    text = "".join(block.text for block in result.content if block.type == "text")
    if result.is_error:
        raise ToolError(text)
    return [ChunkHit(**item) for item in json.loads(text)]
