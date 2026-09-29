"""평가 실행 — `make eval LABEL=baseline`. 설계 §6.

결과: eval/runs/<날짜>-<label>-<커밋>.jsonl (+ .meta.json), 사람 채점 양식 eval/grading/<같은 이름>.csv.
둘 다 gitignore (강의자료 원문 포함).
"""

import argparse
import csv
import json
import subprocess
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import anyio
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.answer import Answer, make_llm, prompt_hash
from app.core.config import get_settings
from app.core.embeddings import OpenAIEmbedder
from app.core.pipeline import PipelineDeps, answer_question
from app.db.models import Document
from app.db.session import make_engine
from app.mcp.server import UserContext
from evaluation.dataset import FROZEN, QUESTIONS, REPO_ROOT, EvalItem, check_frozen, load_items
from evaluation.metrics import none_handled, rate, recall_at_k, source_match

GRADING_FIELDS = ["id", "question", "answer", "key_points", "key_points_ok", "no_hallucination", "note"]


def evaluate_item(item: EvalItem, answer: Answer, latency_ms: int) -> dict:
    return {
        "id": item.id,
        "intent": item.intent,
        "question": item.question,
        "answer": answer.text,
        "sources": [asdict(s) for s in answer.sources],
        "retrieved": [{"source": h.source, "page": h.page, "score": round(h.score, 4)} for h in answer.retrieved],
        "notices": list(answer.notices),
        "citation_ok": answer.citation_ok,
        "latency_ms": latency_ms,
        "recall_at_k": recall_at_k(item, answer.retrieved),
        "source_match": source_match(item, answer.sources),
        "none_handled": none_handled(item, answer.sources),
        "key_points": list(item.key_points),
    }


async def run_items(items: Sequence[EvalItem], answer_fn: Callable[[str], Awaitable[Answer]],
                    clock: Callable[[], float] = time.perf_counter) -> list[dict]:
    records = []
    for item in items:
        started = clock()
        answer = await answer_fn(item.question)
        records.append(evaluate_item(item, answer, round((clock() - started) * 1000)))
    return records


def write_run(records: list[dict], meta: dict, out_dir: Path, name: str) -> tuple[Path, Path]:
    runs, grading = out_dir / "runs", out_dir / "grading"
    runs.mkdir(parents=True, exist_ok=True)
    grading.mkdir(parents=True, exist_ok=True)
    run_path = runs / f"{name}.jsonl"
    grading_path = grading / f"{name}.csv"
    for existing in (run_path, grading_path):
        if existing.exists():
            raise FileExistsError(f"{existing} 이미 있음 — 다른 LABEL을 쓰세요 (예: baseline-2)")
    run_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    (runs / f"{name}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    with grading_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=GRADING_FIELDS)
        writer.writeheader()
        for r in records:
            writer.writerow({"id": r["id"], "question": r["question"], "answer": r["answer"],
                             "key_points": " / ".join(r["key_points"]), "key_points_ok": "",
                             "no_hallucination": "", "note": ""})
    return run_path, grading_path


def _commit() -> str:
    out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    return out.stdout.strip() or "nogit"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m evaluation.run")
    parser.add_argument("--label", required=True)
    args = parser.parse_args(argv)
    items = load_items(QUESTIONS)
    check_frozen(QUESTIONS, FROZEN)
    settings = get_settings()
    embedder = OpenAIEmbedder.from_settings(settings)
    llm = make_llm(settings)
    name = f"{datetime.now().astimezone().date().isoformat()}-{args.label}-{_commit()}"
    with Session(make_engine()) as session:
        # 평가 전용 계정: 모든 과목 수강 (설계 §5 — 의도 측정이 권한에 섞이지 않게)
        courses = frozenset(c for c in session.scalars(select(Document.course_code).distinct()) if c)
        deps = PipelineDeps(session=session, embed_query=lambda q: embedder.embed([q])[0], llm=llm, settings=settings)
        user = UserContext(user_id=0, courses=courses)
        records = anyio.run(run_items, items, lambda q: answer_question(q, user, deps))
    meta = {"label": args.label, "commit": _commit(), "prompt_hash": prompt_hash(),
            "model": settings.generation_model, "effort": settings.generation_effort,
            "k": settings.search_k, "min_score": settings.search_min_score, "n": len(records)}
    _, grading_path = write_run(records, meta, REPO_ROOT / "eval", name)
    print(f"{name}: recall@k {rate(r['recall_at_k'] for r in records)}, "
          f"출처 일치 {rate(r['source_match'] for r in records)}, none {rate(r['none_handled'] for r in records)}")
    print(f"채점 양식: {grading_path}  →  채점 후 make eval-report")


if __name__ == "__main__":
    main()
