import unicodedata

from app.core.answer import CANNOT_ANSWER, NO_EVIDENCE, REFUSED, Answer, Source
from evaluation.dataset import EvalItem, GoldSource
from evaluation.metrics import none_handled, rate, recall_at_k, source_match
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
