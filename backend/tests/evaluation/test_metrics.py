import unicodedata

from app.core.answer import CANNOT_ANSWER, NO_EVIDENCE, REFUSED, Answer, Source
from evaluation.dataset import EvalItem, GoldSource
from evaluation.metrics import (
    intent_ok,
    none_handled,
    rate,
    recall_at_k,
    routing_loss,
    source_match,
)
from tests.fakes import make_hit

ITEM = EvalItem("A01", "q", "academic", (GoldSource("academic/a.pdf", 2),), ("k",))
NONE_ITEM = EvalItem("N01", "q", "none", (), ())


def test_recall_at_k():
    assert recall_at_k(ITEM, [make_hit(1, "academic/b.pdf", 2), make_hit(2, "academic/a.pdf", 2)]) is True
    assert recall_at_k(ITEM, [make_hit(1, "academic/a.pdf", 3)]) is False
    assert recall_at_k(NONE_ITEM, []) is None


def test_source_match():
    assert source_match(ITEM, [Source("academic/a.pdf", 2, None)]) is True
    assert source_match(ITEM, []) is False
    assert source_match(NONE_ITEM, []) is None


def test_none_handled():
    declined = Answer(text=NO_EVIDENCE, sources=[], citation_ok=True, notices=["no_evidence"])
    refused = Answer(text=REFUSED, sources=[], citation_ok=True, notices=["refused"])
    phrase = Answer(text=f"{CANNOT_ANSWER}.", sources=[], citation_ok=True)
    guess = Answer(text="그냥 추측", sources=[], citation_ok=False, notices=["no_citation"])
    cited = Answer(text="답[1]", sources=[Source("academic/a.pdf", 1, None)], citation_ok=True)
    assert none_handled(NONE_ITEM, declined) is True
    assert none_handled(NONE_ITEM, refused) is True
    assert none_handled(NONE_ITEM, phrase) is True
    assert none_handled(NONE_ITEM, guess) is False
    assert none_handled(NONE_ITEM, cited) is False
    assert none_handled(ITEM, declined) is None
    mixed = Answer(text=f"{CANNOT_ANSWER}. 실제로는 9월 1일입니다.", sources=[], citation_ok=False)
    assert none_handled(NONE_ITEM, mixed) is False



def test_rate_ignores_none():
    assert rate([True, False, None, True]) == 2 / 3
    assert rate([None]) is None


def test_recall_at_k_with_nfc_normalization():
    # gold stored as NFC, but hit source is NFD-encoded
    nfc_file = "academic/학사일정.pdf"
    nfd_file = unicodedata.normalize("NFD", nfc_file)

    item = EvalItem("A01", "q", "academic", (GoldSource(nfc_file, 2),), ("k",))

    # hit source is NFD-encoded, but should match NFC gold via normalization
    retrieved = [make_hit(1, nfd_file, 2)]
    assert recall_at_k(item, retrieved) is True


def test_source_match_with_nfc_normalization():
    # gold stored as NFC, but source file is NFD-encoded
    nfc_file = "academic/학사일정.pdf"
    nfd_file = unicodedata.normalize("NFD", nfc_file)

    item = EvalItem("A01", "q", "academic", (GoldSource(nfc_file, 2),), ("k",))

    # source file is NFD-encoded, but should match NFC gold via normalization
    sources = [Source(nfd_file, 2, None)]
    assert source_match(item, sources) is True


BOTH_ITEM = EvalItem("B01", "q", "both", (GoldSource("academic/a.pdf", 2),), ("k",))


def test_intent_ok_requires_valid_label():
    assert intent_ok(BOTH_ITEM, Answer("a", [], True, intent="both", intent_valid=True)) is True
    assert intent_ok(BOTH_ITEM, Answer("a", [], True, intent="both", intent_valid=False)) is False  # 형식 오류로 both 대체
    assert intent_ok(ITEM, Answer("a", [], True, intent="major", intent_valid=True)) is False


def test_intent_ok_is_none_for_baseline():
    assert intent_ok(ITEM, Answer("a", [], True)) is None


def test_none_handled_accepts_out_of_scope():
    answer = Answer("범위 밖", [], True, notices=["out_of_scope"], intent="none", intent_valid=True)
    assert none_handled(NONE_ITEM, answer) is True


def test_none_handled_does_not_credit_decline_caused_by_tool_failure():
    # 도구가 모두 실패해 근거가 없으면 no_evidence가 붙지만, 이는 거절을 잘한 게 아니라 장애다
    broken = Answer(text=NO_EVIDENCE, sources=[], citation_ok=True, notices=["tool_error:search_academic", "no_evidence"])
    assert none_handled(NONE_ITEM, broken) is False


def test_routing_loss_counts_only_misroutes_that_lost_the_evidence():
    # 의도 정확도는 '틀린 분류'를 다 세지만, 사용자 피해는 '틀린 분류 때문에 근거를 못 찾은 경우'뿐이다
    assert routing_loss({"intent_ok": False, "recall_at_k": False}) is True   # A11: none 오분류 → 검색 안 함
    assert routing_loss({"intent_ok": False, "recall_at_k": True}) is False   # academic→both: 근거는 찾음
    assert routing_loss({"intent_ok": False, "recall_at_k": None}) is False   # none 문항: 근거 개념 없음
    assert routing_loss({"intent_ok": True, "recall_at_k": False}) is False   # 검색 자체의 실패 (라우터 무관)
    assert routing_loss({"intent_ok": None, "recall_at_k": False}) is None    # baseline 실행
