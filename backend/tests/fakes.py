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


class FakeLLM:
    """anthropic 클라이언트 대역. beta.messages.create 호출 인자를 기록하고 정해진 답을 돌려준다."""

    def __init__(self, text: str = "", stop_reason: str = "end_turn"):
        self.calls: list[dict] = []
        self.text = text
        self.stop_reason = stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        content = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=self.text)]
        return SimpleNamespace(stop_reason=self.stop_reason, content=content if self.stop_reason != "refusal" else [])
