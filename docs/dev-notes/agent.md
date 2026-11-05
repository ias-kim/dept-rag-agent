# 에이전트 루프 (모델이 도구를 고른다) — 6주차 agent 모드

> 마지막 갱신: 2026-10-27 · **초안** — 코드(`feat/m5-agent`)가 병합되기 전에 계획·결정 로그로 쓴 문서다. 병합 때 함수·테스트 이름을 코드와 대조해 확정한다 · 계획: [`docs/exec-plans/active/2026-10-27-m5-agent.md`](../exec-plans/active/2026-10-27-m5-agent.md) · 설계 §5 · 권한: [`permissions.md`](../design/permissions.md)
>
> 표시: 테스트 이름의 † 는 M5 코드 PR과 함께 들어오는 테스트(이 문서를 쓴 시점에 `main`에 없음).

## 1. 핵심 개념

**workflow는 코드가 고르고, agent는 모델이 고른다.** workflow(`router.md`)는 분류기가 의도를 말하면 코드의 처리 표가 도구를 정한다. agent 모드는 그 단계를 없앤다 — 모델이 질문을 읽고 권한 필터된 도구 목록에서 직접 고르고, 결과를 보고 검색어를 바꿔 다시 부를 수 있다. 얻는 것은 "첫 검색이 빗나가면 다시 찾는" 유연성이고, 잃는 것은 비용·지연의 예측 가능성이다. 그래서 상한이 있다.

**권한은 둘 다 코드가 정한다.** 모델은 자기에게 보이는 도구만 부를 수 있고, 보이는 도구는 MCP `list_tools`가 사용자별로 정한다. 모델 입력에는 역할·수강 과목이 들어가지 않는다. 모델이 도구를 잘못 골라도 SQL 겹이 마지막에 막는다 → [`permissions.md`](../design/permissions.md).

**루프의 네 요소가 `agent.py`의 한 함수(`run_agent`)에서 읽혀야 한다.** 학습·리뷰 목적이라 일부러 한곳에 드러낸다.

| # | 요소 | 코드에서 |
|---|---|---|
| ① | 권한 필터된 도구 목록을 모델에 준다 | `client.list_tools()` → `to_model_tool` → `tools=` |
| ② | 모델의 `tool_use`를 MCP 호출로 바꾼다 | 블록마다 `call_tool(name, input)` |
| ③ | 결과·조각 ID를 누적한다 | `parse_hits` → `chunk_id` 중복 제거(높은 점수 유지) |
| ④ | 끝낸다 | 도구 없는 응답, 또는 **실행한 `tool_use` 블록 4회 상한** → 누적 조각으로 강제 생성 |

**출처 검증과 생성 코드는 workflow와 같은 것을 쓴다.** 최종 답은 `verify_citations`를, 상한 도달 시에는 `generate_answer`를 그대로 쓴다. 검증·생성이 다르면 7주차의 "workflow 대 agent" 비교에 루프 말고 다른 변수가 섞인다.

## 2. 데이터 흐름

```
question (str)
 │  mode="agent"
 ├─ connect(build_server(user, embed_query=감싼 것)) → list_tools()   = 권한 겹 ① (모델에게 보이는 선택지)
 │     질문은 미리 임베딩하지 않는다 (모델이 검색어를 바꾸므로 낭비)
 ├─ messages = [user: "오늘 날짜: YYYY-MM-DD\n\n질문: …"]   ← 역할·과목 없음
 └─ run_agent 루프 ──────────────────────────────────────────────────────────
      │  llm.beta.messages.create(system=agent.md, tools=…, messages=…)
      ├─ tool_use 없음 → 최종 답
      │     refusal → Answer(REFUSED, ["refused"]) · 빈 텍스트 → EMPTY · max_tokens → "truncated" 추가
      │     그 밖 → verify_citations(text, 누적 전체)         ← top-k로 자르지 않음
      └─ tool_use 있음
            messages += assistant: response.content 그대로      ← thinking 블록 포함
            블록마다 (실행 횟수 < 4 인 동안)
              ├─ 이름이 list_tools에 없음 / query가 비어 있지 않은 str 아님
              │     → MCP 호출 없이 is_error tool_result, notices에 invalid_tool_call
              ├─ call_tool → 권한 겹 ② (SQL 조건)
              │     ToolError → is_error tool_result + "tool_error:<도구>", 루프 계속
              │     check_upstream() ← 도구 안에서 임베딩 공급사가 실패했으면 원래 예외를 다시 던진다
              └─ 성공 → parse_hits → 누적 → tool_result "[C번호] (파일 p.쪽)\n본문"
            상한에 닿은 뒤 남은 블록(같은 응답이든 다음 응답이든)은 실행하지 않는다
              → generate_answer(누적 전체, tools 없이) + notices에 tool_limit_reached
            모든 tool_result를 user 메시지 하나로 추가 → 다시 모델 호출

 → Answer(text, sources, notices, intent=None, retrieved=누적, tools_called=[실행한 도구 이름])

평가: evaluate_item → record["tools_called"], meta["agent_prompt_hash"], meta["agent_max_tool_calls"]
```

공지 코드 두 개가 새로 생긴다: `tool_limit_reached`, `invalid_tool_call`. 학생 화면에는 보이지 않게 `frontend/src/notices.js`의 `LABELS`에 넣지 않고 주석의 코드 원천 목록에만 적는다.

한 번의 질문이 도구를 몇 번 불러도 **일일 한도는 1회**만 차감된다 → `test_login_ask_returns_sources_from_seeded_chunk`†.

## 3. 불변 조건과 실패 모드

| 조건 | 깨지면 생기는 문제 | 지키는 장치 |
|---|---|---|
| 출처 검증은 **누적 조각 전체**로 한다 | 마지막 호출의 top-k로만 검증하면 앞선 호출 조각을 인용한 정상 답이 `invalid_citation`이 된다 — 두 번 검색해서 답한 답일수록 틀린 답으로 센다 | `test_agent_citation_from_earlier_call_is_valid`† |
| 다음 assistant 메시지는 `response.content`를 **그대로** 넣는다(thinking 포함) | thinking 블록을 빼면 API가 400을 돌려준다. 도구를 쓰는 질문이 모두 실패하고, 도구 없이 답한 질문만 성공해서 일부만 깨진 것처럼 보인다 | `test_agent_feeds_tool_result_and_preserves_thinking`† |
| 상한 4회는 **실행한 `tool_use` 블록 수**다 (턴 수 아님) | 턴으로 세면 응답 하나에 블록 5개가 와도 5번 검색한다 — 상한이 비용·지연 방어선인데 한 응답에 다 뚫린다. 상한 뒤 블록을 실행하면 같은 이유로 새어 나간다 | `test_agent_cap_counts_blocks_not_turns`†, `test_agent_cap_across_turns`†, `test_agent_four_calls_then_answer_is_not_forced`† |
| 모델의 잘못된 호출(숨은 도구·잘못된 `query`)은 `invalid_tool_call`이고 `tool_error:`가 아니다. MCP를 부르지 않는다 | `tool_error:`와 섞으면 화면에 "일부 자료를 검색하지 못했습니다"가 뜨고, 평가가 장애가 섞인 실행으로 오판해 다시 재게 된다. 숨은 도구를 MCP로 보내면 거절은 되지만 권한 시도가 도구 오류로 위장된다 | `test_agent_hidden_tool_call_is_not_executed`†, `test_agent_non_string_query_is_invalid_call`† |
| 잘못된 호출도 실행 횟수에 센다 | 세지 않으면 모델이 같은 잘못된 호출을 무한히 되풀이해 루프가 끝나지 않는다 | 전용 테스트 없음(계획의 테스트 목록에 없다). 구현 때 `test_agent_hidden_tool_call_is_not_executed`†가 반복 호출에서도 상한에 닿는지 확인하거나 테스트를 더한다 |
| 진짜 도구 장애는 `tool_error:<도구>` + `is_error` 결과로 알리고 루프를 계속한다 | 예외로 올리면 도구 하나의 일시 장애로 답 전체가 사라진다. 조용히 삼키면 장애가 "자료 없음" 답이 된다 | `test_agent_tool_error_is_reported_and_loop_continues`† |
| 임베딩 공급사 장애는 `answer_question` 밖으로 **원래 예외**로 올라간다 | 질문이 아닌 모델이 만든 검색어는 도구 안에서 처음 임베딩된다. MCP가 예외를 `isError`로 바꾸면 모델은 "자료 없음"으로 답하고, API는 200 + 한도 차감으로 끝난다. 사용자는 장애를 "답이 없다"로 받고 한도도 잃는다 | `test_agent_embedding_failure_surfaces`†, `test_agent_embedding_outage_returns_503_and_refunds`† |
| 모델 입력(system·messages)에 역할·수강 과목을 넣지 않는다 | 질문 속 권한 문구가 모델 판단을 흔들 수 있고, 모델이 "권한을 해석"하는 경로가 생긴다. 또 `agent_prompt_hash`는 `agent.md` 파일만 해시하므로 실행 중에 과목을 끼우면 해시가 그대로여서 기록에 드러나지 않는다 | `test_agent_first_message_has_today_and_no_courses`†, `test_no_foreign_major_chunk_reaches_answer_or_model`† |
| 모델에 넘기는 `tools`는 MCP `list_tools` 결과 그대로다 | 코드가 목록을 따로 만들면 겹 1(MCP)과 모델의 선택지가 어긋난다. 게스트에게 `search_major`가 보이는 순간부터 권한 겹 하나가 모델의 자제에 의존한다 | `test_agent_tools_argument_matches_mcp_visibility`†, `test_agent_guest_gets_only_academic_tool`† |
| 학과와 무관한 질문은 도구 없이 "제공된 자료에서 답을 찾을 수 없습니다."로 끝난다 | 출처 없는 거절이 `no_citation`으로 잡히면 none 문항이 전부 틀린 답이 된다. 반대로 출처 없는 근거 없는 주장은 `no_citation`으로 잡혀야 한다 | `test_agent_direct_answer_without_tools`† |
| `refusal`은 content를 읽지 않고 `REFUSED`, 빈 텍스트는 `EMPTY`, `max_tokens`는 `truncated` | 거절·잘림 응답에서 텍스트를 이어 붙이면 잘린 답이 정상 답처럼 나간다 | `test_agent_refusal_and_truncation`† |
| `render_context`는 `render_chunks`를 쓰되 출력은 이전과 바이트 단위로 같다 | workflow·baseline의 모델 입력이 조용히 바뀌어 3~4주차 평가와 비교할 수 없게 된다(`prompt_hash`는 이를 못 잡는다) | `test_render_context_unchanged_after_extracting_render_chunks`† |

외부 요인:
- **Sonnet 장애·타임아웃:** workflow와 같다 — 예외가 올라가 API가 503으로 바꾸고 한도를 돌려준다.
- **`stop_reason == "pause_turn"` 등 `tool_use`가 아닌 나머지:** 최종 응답으로 본다. 텍스트가 비면 `EMPTY`.
- **모델이 같은 검색을 되풀이:** 프롬프트가 억제하지만 코드가 막지는 않는다. 상한(4회)이 막는다.

## 4. 다음 수정

- **7주차 M6:** 도구 선택 정확도 지표(호출한 도구 → 의도 환산), workflow 대 agent 비교표. agent의 `intent`가 `None`이라 지금 의도 정확도로는 비교할 수 없다. 비용·지연(호출 수, 토큰) 기록도 이때 정한다.
- **게스트 agent 공지:** 전공 질문을 한 게스트에게 `major_requires_enrollment` 공지는 붙이지 않는다(모델이 전공 도구를 못 보는 것으로 충분하다고 판단). 필요하면 M6에서 다시 본다.
- **하이브리드 검색(7주차):** 도구 안의 검색이 바뀌어도 에이전트 루프는 그대로여야 한다. 키워드 쪽 쿼리에도 권한 조건이 붙는지 권한 행렬에 행을 더한다.

## 5. 업데이트 시 주의점

- **`agent_max_tool_calls`(상한)를 바꾸면** 평가 meta의 `agent_max_tool_calls`가 달라진다. 이전 `agent-*` 실행과 직접 비교하지 말고 같은 커밋·같은 날 다시 잰다. meta는 모든 모드에 기록되므로 다른 모드 실행과 섞는 실수도 막는다.
- **`agent.md`를 고치면** `agent_prompt_hash`가 바뀐다. 평가셋 36문항에 문장을 맞추지 않는다(`router.md`의 `classify.md` 주의와 같다).
- **`agent.md`의 규칙 1~7은 `answer.md`와 같게 둔다.** 한쪽만 고치면 workflow와 agent의 생성 규칙이 달라져 7주차 비교가 오염된다.
- **`render_chunks`·tool_result 모양을 고치면** 해시가 바뀌지 않는다(`agent.md` 파일만 해시). 모델 입력이 달라졌으니 기준선을 다시 재고 커밋 해시로 구분한다.
- **새 공지 코드를 더하면** `frontend/src/notices.js` 주석의 코드 원천 목록과 이 문서를 같이 고친다. 학생 화면에 보이게 하려면 `LABELS`에도 넣는다(지금 두 코드는 일부러 뺐다).
- **MCP 도구를 추가·변경하면** agent 모드는 `list_tools` 결과를 그대로 모델에 주므로 새 도구가 곧바로 모델의 선택지가 된다. 읽기 전용 규칙(`AGENTS.md` 절대 규칙 2)과 권한 행렬을 먼저 확인한다.
- **`pipeline`의 `check_upstream`을 빼면** 임베딩 장애 테스트(`test_agent_embedding_outage_returns_503_and_refunds`†)가 FAIL해야 한다. 안 하면 그 테스트가 장애를 잡지 못하는 것이니 테스트를 고친다.

## 결정 기록 (2026-10-27)

- agent의 최종 출처 검증은 누적 조각 전체로 한다.
- 상한 4회는 실행한 `tool_use` 블록 수로 센다. 상한 뒤에는 기존 `generate_answer`로 강제 생성해 생성·검증 코드를 workflow와 공유한다.
- 잘못된 호출은 `invalid_tool_call`, 도구 장애는 `tool_error:`로 구분한다. MCP의 인자 검사는 두 번째 방어선으로 남긴다.
- 질문을 미리 임베딩하지 않고, 도구 안 임베딩 예외를 기록했다가 `check_upstream`으로 원래 예외를 다시 던진다.
- `intent`는 `None`. 호출 도구는 `tools_called`로 기록하고 도구 → 의도 환산은 7주차에 정한다.

## 파일 위치

| 파일 | 역할 |
|---|---|
| `backend/app/core/agent.py` | `run_agent`(루프 4요소), `to_model_tool`, `agent_prompt_hash`, 공지 상수 |
| `backend/app/core/prompts/agent.md` | 에이전트 시스템 프롬프트 (SoT) |
| `backend/app/core/answer.py` | `render_chunks`, `Answer.tools_called` |
| `backend/app/core/pipeline.py` | `MODES`, agent 분기, 임베딩 장애 감시(`check_upstream`) |
| `backend/app/core/config.py` | `agent_max_tool_calls` |
| `backend/evaluation/run.py` | `--mode agent`, `tools_called`·`agent_prompt_hash`·`agent_max_tool_calls` 기록 |
| `backend/tests/db/test_agent.py`, `test_permission_matrix.py`, `test_integration.py` | 루프·권한 행렬·로그인→ask→출처 |
