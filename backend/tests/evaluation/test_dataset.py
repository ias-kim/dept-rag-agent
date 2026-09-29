import unicodedata

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


@pytest.mark.parametrize("bad, message", [
    ("key: value", "최상위"),  # 최상위가 매핑
    ("[1, 2, 3]", "#0"),  # 목록 항목이 매핑이 아님 (인덱스 명시)
    ("""
- id: A01
  question: q
  intent: academic
  gold_sources: invalid
  key_points: [k]
""", "gold_sources"),  # gold_sources가 목록이 아님
    ("""
- id: A01
  question: q
  intent: academic
  gold_sources: [invalid]
  key_points: [k]
""", "A01"),  # gold entry가 매핑이 아님
    ("""
- id: A01
  question: q
  intent: academic
  gold_sources: [{page: 1}]
  key_points: [k]
""", "file이 필요함"),  # gold entry의 file 누락
    ("""
- id: A01
  question: q
  intent: academic
  gold_sources: [{file: "", page: 1}]
  key_points: [k]
""", "file이 필요함"),  # gold entry의 file 빈 문자열
    ("""
- id: A01
  question: q
  intent: academic
  gold_sources: [{file: 5, page: 1}]
  key_points: [k]
""", "file"),  # gold entry의 file이 비문자열
    ("""
- question: q
  intent: academic
  gold_sources: [{file: a.pdf, page: 1}]
  key_points: [k]
""", "id"),  # id 누락
    ("""
- id: ""
  question: q
  intent: academic
  gold_sources: [{file: a.pdf, page: 1}]
  key_points: [k]
""", "id"),  # id 빈 문자열
    ("""
- id: 5
  question: q
  intent: academic
  gold_sources: [{file: a.pdf, page: 1}]
  key_points: [k]
""", "id"),  # id가 숫자
    ("""
- id: A01
  question: q
  intent: academic
  gold_sources: [{file: a.pdf, page: 1}]
  key_points: 9월 8일
""", "key_points"),  # key_points가 스칼라
    ("""
- id: A01
  question: q
  intent: academic
  gold_sources: [{file: a.pdf, page: 1}]
  key_points: [1]
""", "key_points"),  # key_points의 원소가 숫자
    ("""
- id: A01
  question: q
  intent: academic
  gold_sources: [{file: a.pdf, page: 1}]
  key_points: [{a: b}]
""", "key_points"),  # key_points의 원소가 dict
])
def test_input_validation_rejects(tmp_path, bad, message):
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


def test_nfc_normalization_in_loader(tmp_path):
    """gold file이 NFD인 경우 NFC로 변환되어 저장되는지 확인"""
    nfd_file = unicodedata.normalize("NFD", "academic/학사일정.pdf")
    nfc_file = unicodedata.normalize("NFC", "academic/학사일정.pdf")

    yaml_content = f"""
- id: A01
  question: 수강신청 정정 기간은?
  intent: academic
  gold_sources:
    - file: {nfd_file}
      page: 2
  key_points: [9월 8일~9월 12일]
"""
    items = load_items(write(tmp_path, yaml_content))
    assert items[0].gold_sources[0].file == nfc_file


def test_none_intent_omitted_lists(tmp_path):
    """none intent일 때 gold_sources/key_points가 omitted인 경우 로드됨"""
    yaml_content = """
- id: N01
  question: 오늘 점심 메뉴 추천해줘
  intent: none
"""
    items = load_items(write(tmp_path, yaml_content))
    assert items[0].id == "N01"
    assert items[0].intent == "none"
    assert items[0].gold_sources == ()
    assert items[0].key_points == ()
