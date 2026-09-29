from app.core.answer import Source
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
    assert none_handled(NONE_ITEM, []) is True
    assert none_handled(NONE_ITEM, [Source("academic/a.pdf", 1, None)]) is False
    assert none_handled(ITEM, []) is None


def test_rate_ignores_none():
    assert rate([True, False, None, True]) == 2 / 3
    assert rate([None]) is None
