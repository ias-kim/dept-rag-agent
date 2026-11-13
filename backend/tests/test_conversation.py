from types import SimpleNamespace

from app.core.conversation import (
    CONDENSED_MAX_CHARS,
    Turn,
    condense_prompt,
    condense_question,
    render_history,
)


class CondenseLLM:
    def __init__(self, text="", stop_reason="end_turn"):
        self.calls = []
        self.text = text
        self.stop_reason = stop_reason
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        content = [SimpleNamespace(type="text", text=self.text)] if self.stop_reason != "refusal" else []
        return SimpleNamespace(stop_reason=self.stop_reason, content=content)


HISTORY = (Turn("MCP에서 Host, Client, Server는 각각 무슨 역할이야?", "Host는 사용자가 쓰는 앱입니다 [1]. Server는 도구를 줍니다 [2]."),)


def condense(llm, question="원격이랑 로컬은 뭐가 달라?", history=HISTORY):
    return condense_question(llm, question, history, model="haiku", max_tokens=200)


def test_rewrites_follow_up_into_standalone_question():
    llm = CondenseLLM("MCP 원격 서버와 로컬 서버는 무엇이 다른가?")
    assert condense(llm) == "MCP 원격 서버와 로컬 서버는 무엇이 다른가?"
    sent = llm.calls[0]
    assert sent["system"] == condense_prompt() and sent["model"] == "haiku"
    user_text = sent["messages"][0]["content"]
    assert "MCP에서 Host" in user_text and "원격이랑 로컬은 뭐가 달라?" in user_text


def test_prior_answer_citation_numbers_are_not_sent():
    # [1] 같은 번호는 이전 답변의 출처 목록에만 뜻이 있다. 남기면 재작성 모델이 검색어에 숫자를 섞는다
    assert "[1]" not in render_history(HISTORY) and "Host는 사용자가 쓰는 앱입니다" in render_history(HISTORY)


def test_refusal_or_empty_output_falls_back_to_original_question():
    assert condense(CondenseLLM(stop_reason="refusal")) == "원격이랑 로컬은 뭐가 달라?"
    assert condense(CondenseLLM("   ")) == "원격이랑 로컬은 뭐가 달라?"


def test_overlong_output_falls_back_to_original_question():
    # 너무 긴 검색어는 임베딩이 4xx로 실패해 500이 되고 한도도 돌려받지 못한다(agent.py QUERY_MAX_CHARS)
    assert condense(CondenseLLM("가" * (CONDENSED_MAX_CHARS + 1))) == "원격이랑 로컬은 뭐가 달라?"


def test_strips_quotes_and_label_the_model_may_add():
    assert condense(CondenseLLM('질문: "MCP 원격 서버와 로컬 서버 차이"')) == "MCP 원격 서버와 로컬 서버 차이"


def test_only_recent_turns_are_used():
    many = tuple(Turn(f"질문{i}", f"답{i}") for i in range(10))
    text = render_history(many)
    assert "질문9" in text and "질문0" not in text


def test_truncated_output_falls_back_to_original_question():
    # max_tokens에서 끊긴 반쪽 문장을 검색어로 쓰면 원래 질문보다 나쁜 검색이 된다
    assert condense(CondenseLLM("MCP 원격 서버와 로컬", stop_reason="max_tokens")) == "원격이랑 로컬은 뭐가 달라?"
