from app.core.answer import (
    CANNOT_ANSWER,
    EMPTY,
    FALLBACK_BETA,
    NO_EVIDENCE,
    REFUSED,
    Source,
    generate_answer,
    prompt_hash,
    system_prompt,
)
from tests.fakes import FakeLLM, make_hit

OPTS = {"model": "claude-sonnet-5-5", "effort": "medium", "max_tokens": 4096}


def test_no_hits_returns_no_evidence_without_calling_llm():
    llm = FakeLLM("무시됨")
    answer = generate_answer(llm, "질문", [], **OPTS)
    assert answer.text == NO_EVIDENCE and answer.sources == [] and llm.calls == []
    assert answer.notices == ["no_evidence"]


def test_citations_are_renumbered_and_sources_built_from_metadata():
    hits = [make_hit(12, "academic/학사일정.pdf", 2, "제3조(기간)"), make_hit(7, "academic/성적.pdf", 5)]
    llm = FakeLLM("정정 기간은 9월 8일부터다[C12]. 성적은 12월에 나온다[C7][C12].")
    answer = generate_answer(llm, "정정 기간?", hits, **OPTS)
    assert answer.text == "정정 기간은 9월 8일부터다[1]. 성적은 12월에 나온다[2][1]."
    assert answer.sources == [Source("academic/학사일정.pdf", 2, "제3조(기간)"), Source("academic/성적.pdf", 5, None)]
    assert answer.citation_ok is True
    assert [h.chunk_id for h in answer.retrieved] == [12, 7]


def test_unretrieved_citation_is_dropped():
    answer = generate_answer(FakeLLM("지어낸 규정이다[C99]."), "q", [make_hit(12)], **OPTS)
    assert answer.text == "지어낸 규정이다."
    assert answer.sources == []
    assert answer.citation_ok is False and answer.notices == ["invalid_citation", "no_citation"]


def test_refusal_does_not_read_content():
    answer = generate_answer(FakeLLM(stop_reason="refusal"), "q", [make_hit(1)], **OPTS)
    assert answer.text == REFUSED and answer.sources == [] and answer.notices == ["refused"]


def test_request_shape():
    llm = FakeLLM("답[C3]")
    generate_answer(llm, "휴학 신청은?", [make_hit(3, section="제9조(휴학)")], **OPTS)
    kw = llm.calls[0]
    assert kw["model"] == "claude-sonnet-5-5" and kw["max_tokens"] == 4096
    assert kw["betas"] == [FALLBACK_BETA] and kw["fallbacks"] == "default"
    assert kw["output_config"] == {"effort": "medium"}
    assert not {"temperature", "top_p", "top_k"} & set(kw)
    assert kw["system"] == system_prompt()
    user_text = kw["messages"][0]["content"]
    assert kw["messages"][0]["role"] == "user"
    assert "[C3]" in user_text and "제9조(휴학)" in user_text and "휴학 신청은?" in user_text


def test_prompt_hash_is_stable_short_hex():
    assert prompt_hash() == prompt_hash() and len(prompt_hash()) == 12


def test_truncated_answer_is_flagged():
    llm = FakeLLM(text="답[C1]", stop_reason="max_tokens")
    answer = generate_answer(llm, "q", [make_hit(1)], **OPTS)
    assert answer.text == "답[1]"
    assert answer.notices == ["truncated"]
    assert answer.citation_ok is True


def test_empty_response_is_flagged():
    answer = generate_answer(FakeLLM(text="   "), "q", [make_hit(1)], **OPTS)
    assert answer.text == EMPTY
    assert answer.sources == []
    assert answer.notices == ["empty"]


def test_preexisting_bracket_numbers_are_neutralized():
    answer = generate_answer(FakeLLM("참고문헌 [1] 에 따르면 X다[C7]."), "q", [make_hit(7)], **OPTS)
    assert answer.text == "참고문헌 ［1］ 에 따르면 X다[1]."
    assert len(answer.sources) == 1


def test_list_form_citations_are_expanded():
    hits = [make_hit(7), make_hit(12)]
    for raw in ("X[C7, C12]", "X[C7,C12]", "X[C7, 12]"):
        answer = generate_answer(FakeLLM(raw), "q", hits, **OPTS)
        assert answer.text == "X[1][2]", raw
        assert answer.citation_ok is True and len(answer.sources) == 2


def test_list_form_with_invalid_id_drops_it_and_flags():
    answer = generate_answer(FakeLLM("X[C7, C99]"), "q", [make_hit(7)], **OPTS)
    assert answer.text == "X[1]" and answer.citation_ok is False
    assert answer.notices == ["invalid_citation"]


def test_malformed_marker_is_removed_and_flagged():
    for raw in ("X[c7]", "X［C7］", "X[C7 참고]"):
        answer = generate_answer(FakeLLM(raw), "q", [make_hit(7)], **OPTS)
        assert answer.text == "X", raw
        assert "invalid_citation" in answer.notices and answer.citation_ok is False


def test_answer_without_citation_gets_notice():
    answer = generate_answer(FakeLLM("그냥 답"), "q", [make_hit(7)], **OPTS)
    assert answer.notices == ["no_citation"] and answer.citation_ok is False


def test_cannot_answer_phrase_needs_no_citation():
    answer = generate_answer(FakeLLM(f"{CANNOT_ANSWER}."), "q", [make_hit(7)], **OPTS)
    assert answer.notices == [] and answer.citation_ok is True
