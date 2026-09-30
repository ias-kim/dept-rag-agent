"""폴더(→ 나중에 S3) ↔ 색인 동기화. 해시가 같으면 건너뛰고, 전체를 한 트랜잭션으로 처리한다. 설계 결정 11."""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.embeddings import Embedder
from app.core.ingest.chunking import STRATEGIES, build_chunks
from app.core.ingest.clean import clean_pages
from app.core.ingest.markdown import extract_markdown
from app.core.ingest.pdf import Page, extract_pages
from app.db.models import Chunk, Document

SUFFIXES = (".pdf", ".md")


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
    if not root.is_dir():
        raise ValueError(f"자료 폴더가 없습니다: {root}")
    files: list[SourceFile] = []
    misplaced: list[str] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in SUFFIXES:
            continue
        rel = p.relative_to(root)
        parts = rel.parts
        if any(part.startswith(".") for part in parts):  # ._x.pdf, .hidden/ 등
            continue
        if len(parts) == 1 and p.suffix.lower() == ".md":  # data/MANIFEST.md 같은 설명 파일
            continue
        if parts[0] == "academic":
            files.append(SourceFile(rel.as_posix(), p, "academic", None))
        elif parts[0] == "major" and len(parts) >= 3:
            files.append(SourceFile(rel.as_posix(), p, "major", parts[1].upper()))
        else:
            misplaced.append(rel.as_posix())
    if misplaced:
        raise ValueError(
            "위치가 잘못된 자료 파일 (academic/… 또는 major/<과목코드>/…): " + ", ".join(misplaced)
        )
    return files


def load_pages(path: Path) -> list[Page]:
    if path.suffix.lower() == ".md":
        return extract_markdown(path)
    return clean_pages(extract_pages(path))  # 머리글·꼬리말·쪽번호 제거


def _guard_against_wipe(root: Path, sources: list[SourceFile], existing: dict[str, Document]) -> None:
    """--prune 없이는 자료 폴더가 통째로 비었거나 스코프 폴더가 사라진 상태로 색인을 지우지 않는다."""
    if not sources and existing:
        raise ValueError("자료 폴더에 파일이 없습니다 — 전체 삭제하려면 --prune")
    for scope in ("academic", "major"):
        if not (root / scope).is_dir() and any(d.scope == scope for d in existing.values()):
            raise ValueError(f"{root / scope} 폴더가 없습니다 — 해당 스코프 문서를 모두 삭제하려면 --prune")


def sync_folder(
    session: Session, root: Path, embedder: Embedder, *, max_chars: int, overlap: int, prune: bool = False,
    strategy: str = "structure",
) -> SyncReport:
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown chunk strategy: {strategy!r} (choose from {STRATEGIES})")
    sources = discover(root)  # 잘못된 위치면 여기서 끝 — DB 변경 없음
    report = SyncReport()
    try:
        existing = {d.path: d for d in session.scalars(select(Document))}
        if not prune:
            _guard_against_wipe(root, sources, existing)
        seen: set[str] = set()
        for sf in sources:
            seen.add(sf.rel_path)
            sha = hashlib.sha256(sf.abs_path.read_bytes()).hexdigest()
            old = existing.get(sf.rel_path)
            if old is not None and (old.sha256, old.scope, old.course_code) == (sha, sf.scope, sf.course_code):
                report.unchanged.append(sf.rel_path)
                continue
            pages = load_pages(sf.abs_path)
            drafts = build_chunks(pages, strategy=strategy, max_chars=max_chars, overlap=overlap)
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
