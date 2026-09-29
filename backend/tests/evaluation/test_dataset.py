import pytest

from evaluation.dataset import EvalItem, GoldSource, check_frozen, freeze, load_items

VALID = """
- id: A01
  question: 수강신청 정정 기간은?
  intent: academic
  gold_sources: [{file: academic/학사일정.pdf, page: 2}]
  key_points: [9월 8일~9월 12일]
- id: N01
  question: 오늘 점심 메뉴 추천해줘
  intent: none
  gold_sources: []
  key_points: []
"""


def write(tmp_path, text, name="q.yaml"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_load_valid_items(tmp_path):
    items = load_items(write(tmp_path, VALID))
    assert items[0] == EvalItem("A01", "수강신청 정정 기간은?", "academic",
                                (GoldSource("academic/학사일정.pdf", 2),), ("9월 8일~9월 12일",))
    assert items[1].intent == "none" and items[1].gold_sources == ()


@pytest.mark.parametrize("bad, message", [
    (VALID.replace("id: N01", "id: A01"), "중복"),
    (VALID.replace("intent: academic", "intent: other"), "intent"),
    (VALID.replace("gold_sources: [{file: academic/학사일정.pdf, page: 2}]", "gold_sources: []"), "gold_sources"),
    (VALID.replace("gold_sources: []\n  key_points: []", "gold_sources: [{file: a.pdf, page: 1}]\n  key_points: []"), "none"),
    (VALID.replace("page: 2", "page: 0"), "page"),
    (VALID.replace("key_points: [9월 8일~9월 12일]", "key_points: []"), "key_points"),
])
def test_invalid_items_rejected(tmp_path, bad, message):
    with pytest.raises(ValueError, match=message):
        load_items(write(tmp_path, bad))


def test_check_frozen_passes_when_unfrozen_or_matching(tmp_path):
    q = write(tmp_path, VALID)
    check_frozen(q, tmp_path / "FROZEN")  # FROZEN 없음 → 통과
    freeze(q, tmp_path / "FROZEN")
    check_frozen(q, tmp_path / "FROZEN")


def test_check_frozen_rejects_changed_file(tmp_path):
    q = write(tmp_path, VALID)
    freeze(q, tmp_path / "FROZEN")
    q.write_text(VALID.replace("정정 기간은?", "정정 기간이 언제야?"), encoding="utf-8")
    with pytest.raises(ValueError, match="동결"):
        check_frozen(q, tmp_path / "FROZEN")
