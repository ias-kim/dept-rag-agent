import pytest

from app.core.router import Classification, Plan, classify, parse_intent, plan
from app.mcp.server import TOOL_ACADEMIC, TOOL_MAJOR, UserContext
from tests.fakes import FakeLLM

STUDENT = UserContext(user_id=1, courses=frozenset({"AGENT"}))
GUEST = UserContext(user_id=2, courses=frozenset())


@pytest.mark.parametrize("raw, expected", [
    ("academic", "academic"), (" Major.\n", "major"), ("BOTH", "both"), ("none", "none"),
    ("학사", None), ("academic because ...", None), ("", None),
])
def test_parse_intent(raw, expected):
    assert parse_intent(raw) == expected


def test_classify_sends_only_question_without_role_or_sampling():
    llm = FakeLLM(classify_text="major")
    result = classify(llm, "MCP Host가 뭐야?", model="claude-haiku-4-5-20251001", max_tokens=16)
    assert result == Classification("major", True, "major")
    call = llm.classify_calls[0]
    assert call["model"] == "claude-haiku-4-5-20251001" and call["max_tokens"] == 16
    assert call["messages"] == [{"role": "user", "content": "MCP Host가 뭐야?"}]
    assert not {"temperature", "top_p", "top_k", "output_config"} & set(call)
    assert "AGENT" not in call["system"]


def test_classify_garbage_falls_back_to_both_invalid():
    result = classify(FakeLLM(classify_text="잘 모르겠어요"), "q", model="m", max_tokens=16)
    assert (result.intent, result.valid) == ("both", False)


def test_classify_refusal_falls_back_to_both_invalid():
    result = classify(FakeLLM(classify_stop="refusal"), "q", model="m", max_tokens=16)
    assert result == Classification("both", False, "")


@pytest.mark.parametrize("intent, user, expected", [
    ("academic", STUDENT, Plan((TOOL_ACADEMIC,), ())),
    ("academic", GUEST, Plan((TOOL_ACADEMIC,), ())),
    ("major", STUDENT, Plan((TOOL_MAJOR,), ())),
    ("major", GUEST, Plan((), ("major_requires_enrollment",))),
    ("both", STUDENT, Plan((TOOL_ACADEMIC, TOOL_MAJOR), ())),
    ("both", GUEST, Plan((TOOL_ACADEMIC,), ("major_requires_enrollment",))),
    ("none", STUDENT, Plan((), ("out_of_scope",))),
    ("none", GUEST, Plan((), ("out_of_scope",))),
])
def test_plan_table(intent, user, expected):
    assert plan(intent, user) == expected


def test_plan_rejects_unknown_intent():
    with pytest.raises(ValueError):
        plan("other", STUDENT)
