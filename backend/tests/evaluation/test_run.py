import csv
import json
from datetime import date

import pytest

from app.core.answer import Answer, Source
from evaluation.dataset import EvalItem, GoldSource
from evaluation.run import evaluate_item, main, prepare_run, require_frozen, run_items, write_run
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
    assert rec["predicted_intent"] is None and rec["intent_ok"] is None  # baseline 답변


def test_evaluate_item_records_prediction_without_overwriting_gold_intent():
    answer = Answer("a", [], True, intent="major", intent_valid=True)
    rec = evaluate_item(ITEM, answer, 1)
    assert rec["intent"] == "academic"  # 정답 라벨은 그대로
    assert (rec["predicted_intent"], rec["intent_valid"], rec["intent_ok"]) == ("major", True, False)


def test_unknown_mode_is_rejected_before_any_work():
    with pytest.raises(SystemExit):
        main(["--label", "x", "--mode", "nope"])


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


def test_write_run_refuses_to_overwrite_existing_run(tmp_path):
    rec = evaluate_item(ITEM, ANSWER, 10)
    _, grading_path = write_run([rec], {"label": "baseline"}, tmp_path, "same")
    before = grading_path.read_bytes()
    with pytest.raises(FileExistsError, match="LABEL"):
        write_run([rec], {"label": "baseline"}, tmp_path, "same")
    assert grading_path.read_bytes() == before


TODAY = date(2026, 10, 1)


def test_prepare_run_returns_name(tmp_path):
    assert prepare_run("baseline", tmp_path, "abc1234", TODAY) == "2026-10-01-baseline-abc1234"


@pytest.mark.parametrize("label", ["", "a b", "a/b", "../x", "베이스 라인"])
def test_prepare_run_rejects_bad_label(tmp_path, label):
    with pytest.raises(ValueError, match="label"):
        prepare_run(label, tmp_path, "abc1234", TODAY)


def test_prepare_run_rejects_existing_outputs(tmp_path):
    name = "2026-10-01-baseline-abc1234"
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / f"{name}.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(FileExistsError):
        prepare_run("baseline", tmp_path, "abc1234", TODAY)
    (tmp_path / "runs" / f"{name}.jsonl").unlink()
    (tmp_path / "grading").mkdir()
    (tmp_path / "grading" / f"{name}.csv").write_text("", encoding="utf-8")
    with pytest.raises(FileExistsError):
        prepare_run("baseline", tmp_path, "abc1234", TODAY)


def test_require_frozen_needs_frozen_file(tmp_path):
    q = tmp_path / "questions.yaml"
    q.write_text("- id: A\n", encoding="utf-8")
    with pytest.raises(ValueError, match="make eval-freeze"):
        require_frozen(q, tmp_path / "FROZEN")


def test_evaluate_item_counts_tool_errors():
    answer = Answer("a", [], True, notices=["tool_error:search_major", "no_evidence"])
    assert evaluate_item(ITEM, answer, 1)["tool_errors"] == 1


def test_evaluate_item_records_tools_called():
    answer = Answer("a", [], True, tools_called=["search_academic", "search_major"])
    rec = evaluate_item(ITEM, answer, 1)
    assert rec["tools_called"] == ["search_academic", "search_major"]
    assert rec["intent_ok"] is None  # agent는 분류기가 없다 — 의도 정확도에 섞이지 않는다


def test_agent_mode_passes_argument_parsing(monkeypatch):
    from evaluation import run

    class Reached(Exception):
        pass

    def stop(*args, **kwargs):
        raise Reached

    monkeypatch.setattr(run, "prepare_run", stop)
    with pytest.raises(Reached):
        main(["--label", "x", "--mode", "agent"])


def test_run_meta_records_agent_settings_for_every_mode():
    from app.core.agent import agent_prompt_hash
    from app.core.config import Settings
    from evaluation.run import run_meta

    meta = run_meta("router-v3", "workflow", "abc1234", Settings(_env_file=None, agent_max_tool_calls=4), n=36)
    assert meta["agent_prompt_hash"] == agent_prompt_hash() and meta["agent_max_tool_calls"] == 4
    assert meta["mode"] == "workflow" and meta["n"] == 36 and meta["commit"] == "abc1234"


def test_evaluate_item_recall_uses_top_k_of_accumulated_agent_hits():
    hits = [make_hit(1, "academic/b.pdf", 2, score=0.9), make_hit(2, "academic/a.pdf", 2, score=0.4)]
    answer = Answer("a", [], True, retrieved=hits, tools_called=["search_academic", "search_academic"])
    assert evaluate_item(ITEM, answer, 1, k=1)["recall_at_k"] is False
    assert evaluate_item(ITEM, answer, 1, k=2)["recall_at_k"] is True


def test_agent_prompt_hash_covers_tool_definitions(monkeypatch):
    # 도구 설명도 모델의 도구 선택을 바꾼다 — 해시에 없으면 설명만 바꾼 실행이 같은 조건으로 보인다
    from mcp import types

    from app.core import agent

    before = agent.agent_prompt_hash()
    monkeypatch.setattr(agent, "visible_tools", lambda user: [
        types.Tool(name="search_academic", description="바뀐 설명", inputSchema={"type": "object"})])
    assert agent.agent_prompt_hash() != before
