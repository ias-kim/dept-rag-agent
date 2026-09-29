import pytest

from evaluation.dataset import FROZEN, QUESTIONS, check_frozen, load_items


@pytest.mark.skipif(not QUESTIONS.exists(), reason="eval/questions.yaml 작성 전")
def test_real_eval_set_is_valid_and_frozen():
    items = load_items(QUESTIONS)
    assert len(items) >= 1
    check_frozen(QUESTIONS, FROZEN)
