"""폴더(→ 나중에 S3) ↔ 색인 동기화. 해시가 같으면 건너뛰고, 전체를 한 트랜잭션으로 처리한다. 설계 결정 11."""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.embeddings import Embedder
from app.core.ingest.chunking import chunk_pages
from app.core.ingest.pdf import extract_pages
from app.db.models import Chunk, Document


@dataclass(frozen=True)
class SourceFile:
    rel_path: str
    abs_path: Path
    scope: str
    course_code: str | None


@dataclass
class SyncReport:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    empty: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"추가 {len(self.added)} · 갱신 {len(self.updated)} · 삭제 {len(self.removed)} · 변경 없음 {len(self.unchanged)}"
        ]
        if self.empty:
            lines.append("⚠️ 텍스트 없음(스캔 PDF?): " + ", ".join(self.empty))
        return "\n".join(lines)


def discover(root: Path) -> list[SourceFile]:
    files: list[SourceFile] = []
    misplaced: list[str] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() != ".pdf":
            continue
        rel = p.relative_to(root)
        parts = rel.parts
        if parts[0] == "academic":
            files.append(SourceFile(rel.as_posix(), p, "academic", None))
        elif parts[0] == "major" and len(parts) >= 3:
            files.append(SourceFile(rel.as_posix(), p, "major", parts[1].upper()))
        else:
            misplaced.append(rel.as_posix())
    if misplaced:
        raise ValueError(
            "위치가 잘못된 PDF (academic/… 또는 major/<과목코드>/…): " + ", ".join(misplaced)
        )
    return files


def sync_folder(session: Session, root: Path, embedder: Embedder, *, max_chars: int, overlap: int) -> SyncReport:
    sources = discover(root)  # 잘못된 위치면 여기서 끝 — DB 변경 없음
    report = SyncReport()
    try:
        existing = {d.path: d for d in session.scalars(select(Document))}
        seen: set[str] = set()
        for sf in sources:
            seen.add(sf.rel_path)
            sha = hashlib.sha256(sf.abs_path.read_bytes()).hexdigest()
            old = existing.get(sf.rel_path)
            if old is not None and (old.sha256, old.scope, old.course_code) == (sha, sf.scope, sf.course_code):
                report.unchanged.append(sf.rel_path)
                continue
            drafts = chunk_pages(extract_pages(sf.abs_path), max_chars=max_chars, overlap=overlap)
            vectors = embedder.embed([d.text for d in drafts]) if drafts else []
            if old is not None:
                session.delete(old)
                session.flush()  # 같은 path로 다시 넣기 전에 삭제를 먼저 반영
            doc = Document(scope=sf.scope, course_code=sf.course_code, path=sf.rel_path, sha256=sha)
            session.add(doc)
            session.flush()
            session.add_all(
                Chunk(document_id=doc.id, page=d.page, section=d.section, ord=d.ord, text=d.text,
                      embedding=v, scope=sf.scope, course_code=sf.course_code)
                for d, v in zip(drafts, vectors, strict=True)
            )
            (report.updated if old is not None else report.added).append(sf.rel_path)
            if not drafts:
                report.empty.append(sf.rel_path)
        for path, doc in existing.items():
            if path not in seen:
                session.delete(doc)
                report.removed.append(path)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return report
