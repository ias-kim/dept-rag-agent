import zlib
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace

from fpdf import FPDF
from sqlalchemy.orm import Session

from app.db.models import EMBEDDING_DIM, Chunk, Document
from app.db.search import ChunkHit


def unit(i: int) -> list[float]:
    """i번 축만 1인 단위 벡터. 같은 i끼리 코사인 거리 0, 다른 i끼리 1."""
    v = [0.0] * EMBEDDING_DIM
    v[i % EMBEDDING_DIM] = 1.0
    return v


def make_pdf(path: Path, pages: Sequence[str]) -> Path:
    """테스트용 PDF. 한국어 폰트가 없으므로 ASCII만 쓴다. 빈 문자열이면 텍스트 없는 페이지."""
    pdf = FPDF()
    pdf.set_font("Helvetica", size=12)
    for text in pages:
        pdf.add_page()
        if text:
            pdf.multi_cell(0, 8, text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(pdf.output()))
    return path


class FakeEmbedder:
    """텍스트 CRC로 축을 고르는 결정론적 임베더. fail_on_call번째 호출에서 예외."""

    def __init__(self, fail_on_call: int | None = None):
        self.calls = 0
        self.fail_on_call = fail_on_call

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        if self.fail_on_call is not None and self.calls == self.fail_on_call:
            raise RuntimeError("fake embedding failure")
        return [unit(zlib.crc32(t.encode())) for t in texts]


def seed_chunks(session: Session, specs: Sequence[tuple[str, str, str | None, int]]) -> None:
    """(path, scope, course_code, axis)마다 문서 1개·조각 1개를 넣는다. 조각 임베딩은 unit(axis)."""
    for path, scope, course, axis in specs:
        doc = Document(scope=scope, course_code=course, path=path, sha256="0" * 64)
        session.add(doc)
        session.flush()
        session.add(Chunk(document_id=doc.id, page=1, section=None, ord=0, text=f"{path} 본문",
                          embedding=unit(axis), scope=scope, course_code=course))
    session.flush()


def make_hit(chunk_id: int, source: str = "academic/a.pdf", page: int = 1,
             section: str | None = None, score: float = 0.9) -> ChunkHit:
    scope = "major" if source.startswith("major/") else "academic"
    course = source.split("/")[1] if scope == "major" else None
    return ChunkHit(chunk_id=chunk_id, text=f"조각 {chunk_id} 내용", source=source, page=page,
                    section=section, scope=scope, course_code=course, score=score)


def text_reply(text: str, stop_reason: str = "end_turn") -> SimpleNamespace:
    """에이전트 스크립트용 최종 응답. 실제 응답처럼 thinking 블록이 앞에 온다."""
    content = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)]
    return SimpleNamespace(stop_reason=stop_reason, content=content if stop_reason != "refusal" else [])


def tool_use_reply(*blocks: tuple[str, str, dict]) -> SimpleNamespace:
    """에이전트 스크립트용 도구 요청 응답. blocks = (tool_use_id, 도구 이름, 입력)."""
    content = [SimpleNamespace(type="thinking", thinking="")]
    content += [SimpleNamespace(type="tool_use", id=i, name=n, input=inp) for i, n, inp in blocks]
    return SimpleNamespace(stop_reason="tool_use", content=content)


class FakeLLM:
    """anthropic 클라이언트 대역. 생성(beta.messages.create)과 분류(messages.create) 호출을 따로 기록한다.

    script가 있으면 beta.messages.create가 호출마다 다음 응답을 차례로 돌려준다(에이전트 루프용).
    """

    def __init__(self, text: str = "", stop_reason: str = "end_turn", *, classify_text: str = "academic",
                 classify_stop: str = "end_turn", script: Sequence[SimpleNamespace] | None = None):
        self.script = list(script) if script is not None else None
        self.calls: list[dict] = []
        self.classify_calls: list[dict] = []
        self.text = text
        self.stop_reason = stop_reason
        self.classify_text = classify_text
        self.classify_stop = classify_stop
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self.messages = SimpleNamespace(create=self._classify)

    def _create(self, **kwargs):
        # 루프가 같은 messages 리스트에 계속 덧붙이므로 호출 시점 상태를 복사해 둔다
        self.calls.append({**kwargs, "messages": list(kwargs.get("messages", []))})
        if self.script is not None:
            return self.script.pop(0)
        content = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=self.text)]
        return SimpleNamespace(stop_reason=self.stop_reason, content=content if self.stop_reason != "refusal" else [])

    def _classify(self, **kwargs):
        self.classify_calls.append(kwargs)
        content = [SimpleNamespace(type="text", text=self.classify_text)] if self.classify_stop != "refusal" else []
        return SimpleNamespace(stop_reason=self.classify_stop, content=content)
