import csv
import json

from evaluation.report import build_report, load_grading, summarize


def make_run(out, name, records, meta, grading_rows=None):
    (out / "runs").mkdir(parents=True, exist_ok=True)
    (out / "runs" / f"{name}.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    (out / "runs" / f"{name}.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    if grading_rows is not None:
        (out / "grading").mkdir(parents=True, exist_ok=True)
        with (out / "grading" / f"{name}.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id", "key_points_ok", "no_hallucination"])
            w.writeheader()
            w.writerows(grading_rows)


RECORDS = [
    {"id": "A01", "recall_at_k": True, "source_match": True, "none_handled": None, "citation_ok": True, "latency_ms": 100},
    {"id": "A02", "recall_at_k": False, "source_match": False, "none_handled": None, "citation_ok": False, "latency_ms": 300},
    {"id": "N01", "recall_at_k": None, "source_match": None, "none_handled": True, "citation_ok": True, "latency_ms": 200},
]


def test_load_grading_requires_both_marks(tmp_path):
    make_run(tmp_path, "r", RECORDS, {}, [
        {"id": "A01", "key_points_ok": "O", "no_hallucination": "O"},
        {"id": "A02", "key_points_ok": "O", "no_hallucination": "X"},
        {"id": "N01", "key_points_ok": "", "no_hallucination": ""},
    ])
    assert load_grading(tmp_path / "grading" / "r.csv") == {"A01": True, "A02": False, "N01": None}


def test_summarize_rates():
    s = summarize({"label": "baseline"}, RECORDS, {"A01": True, "A02": False, "N01": None})
    assert s["n"] == 3 and s["recall_at_k"] == 0.5 and s["source_match"] == 0.5
    assert s["none_handled"] == 1.0 and s["answer_accuracy"] == 0.5 and s["graded"] == 2
    assert s["latency_p50_ms"] == 200


def test_build_report_is_deterministic_and_marks_ungraded(tmp_path):
    make_run(tmp_path, "2026-10-01-baseline-abc", RECORDS, {"label": "baseline", "prompt_hash": "p1"})
    first = build_report(tmp_path)
    assert first == build_report(tmp_path)
    assert first.startswith("<!-- DO NOT EDIT")
    assert "2026-10-01-baseline-abc" in first and "50.0%" in first and "—" in first
