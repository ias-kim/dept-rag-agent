import csv
import json

import pytest

from app.core.answer import Answer, Source
from evaluation.dataset import EvalItem, GoldSource
from evaluation.run import evaluate_item, run_items, write_run
from tests.fakes import make_hit

ITEM = EvalItem("A01", "정정 기간?", "academic", (GoldSource("academic/a.pdf", 2),), ("9월 8일",))
ANSWER = Answer(text="9월 8일부터[1]", sources=[Source("academic/a.pdf", 2, None)], citation_ok=True,
                retrieved=[make_hit(1, "academic/a.pdf", 2)])


def test_evaluate_item_record():
    rec = evaluate_item(ITEM, ANSWER, 1234)
    assert rec["id"] == "A01" and rec["intent"] == "academic" and rec["latency_ms"] == 1234
    assert rec["recall_at_k"] is True and rec["source_match"] is True and rec["none_handled"] is None
    assert rec["sources"] == [{"file": "academic/a.pdf", "page": 2, "section": None}]
    assert rec["retrieved"] == [{"source": "academic/a.pdf", "page": 2, "score": 0.9}]


@pytest.mark.anyio
async def test_run_items_measures_latency_in_order():
    ticks = iter([0.0, 0.5, 1.0, 3.0])

    async def answer_fn(question):
        return ANSWER

    records = await run_items([ITEM, ITEM], answer_fn, clock=lambda: next(ticks))
    assert [r["latency_ms"] for r in records] == [500, 2000]


def test_write_run_creates_jsonl_meta_and_grading_template(tmp_path):
    rec = evaluate_item(ITEM, ANSWER, 10)
    run_path, grading_path = write_run([rec], {"label": "baseline"}, tmp_path, "2026-10-01-baseline-abc1234")
    assert json.loads(run_path.read_text(encoding="utf-8").splitlines()[0])["id"] == "A01"
    assert json.loads((tmp_path / "runs" / "2026-10-01-baseline-abc1234.meta.json").read_text())["label"] == "baseline"
    rows = list(csv.DictReader(grading_path.open(encoding="utf-8-sig")))
    assert rows[0]["id"] == "A01" and rows[0]["key_points"] == "9월 8일"
    assert rows[0]["key_points_ok"] == "" and rows[0]["no_hallucination"] == ""
