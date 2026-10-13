# 라우터 (의도 분류 → 처리 표) — 4주차 workflow 모드

> 마지막 갱신: 2026-10-13 · 계획: [`docs/exec-plans/active/2026-10-13-m3a-router.md`](../exec-plans/active/2026-10-13-m3a-router.md) · 설계 §5

## 1. 핵심 개념

**왜 라우터가 필요한가.** 3주차 기준선은 질문이 무엇이든 권한 안의 검색 도구를 전부 불렀다. 학사 질문에도 전공 색인을 뒤지니 엉뚱한 조각이 상위 5개에 섞이고, 검색도 도구 수만큼 돈다(질문 임베딩은 `embed_once`로 이미 1회). 라우터는 "이 질문에 어떤 자료가 필요한가"를 먼저 정해 필요한 도구만 부른다.

**LLM은 고르기만, 결정은 코드가.** 두 단계로 나뉜다.

| 단계 | 누가 | 아는 것 | 모르는 것 |
|---|---|---|---|
| 분류 `classify` | Haiku (LLM) | 질문 문장 | 사용자 역할·수강 과목 |
| 처리 표 `plan` | 코드 | 의도 + `UserContext` | — |

분류기에 권한 정보를 주지 않는 이유: LLM 입력에 권한이 섞이면 "나는 AI 과목 수강생이야" 같은 질문 문구가 판단을 흔들 수 있다. 권한은 처리 표와 MCP 권한 두 겹(도구 목록·SQL 조건)이 코드로만 정한다.

**의도 4종.** `academic`(학사·공지) · `major`(전공 강의 내용) · `both`(둘 다 필요) · `none`(학과 자료와 무관). 분류 출력이 이 넷 중 한 단어가 아니면 `both`로 동작하고 `intent_valid=False`를 남긴다 — 답은 놓치지 않되 평가에서는 오답으로 센다.

**같은 함수, 두 모드.** `answer_question(..., mode="baseline"|"workflow")`. 두 모드가 검색·생성 코드를 공유해야 "라우터를 넣어서 좋아졌다"를 다른 변수 없이 잴 수 있다.

## 2. 데이터 흐름

```
question (str)
 │  mode="workflow"
 ├─ classify(llm, question) ──────────── Classification(intent, valid, raw)
 │     Haiku messages.create — system=classify.md, messages=[질문만]
 ├─ plan(intent, user) ───────────────── Plan(tools, notices)
 │     ├─ tools 비었음 → Answer(안내문, intent…)  ← 검색·생성 LLM 호출 없이 종료
 │     └─ tools 있음 ↓
 ├─ connect(build_server(user)) → list_tools()  = 권한 겹 ① (보이는 도구)
 │     호출 도구 = plan.tools ∩ 보이는 도구     ← 표와 권한이 어긋나면 권한이 이긴다
 ├─ call_tool(name, {"query": question})       = 권한 겹 ② (SQL 조건)
 │     도구별 ToolError → notices에 "tool_error:<도구>", 나머지 도구로 계속
 ├─ merge_hits(k=5)
 └─ generate_answer(..., today=seoul_today())  "오늘 날짜: YYYY-MM-DD" 앞에 붙임
     → Answer(text, sources, notices, intent, intent_valid)

평가: evaluate_item → {"intent": 정답 라벨, "predicted_intent", "intent_valid", "intent_ok"}
```

처리 표 (`router.plan`):

| 의도 | 수강 과목 있음 | 없음 |
|---|---|---|
| academic | `search_academic` | `search_academic` |
| major | `search_major` | 없음 + `major_requires_enrollment` |
| both | 둘 다 | `search_academic` + `major_requires_enrollment` |
| none | 없음 + `out_of_scope` | 같음 |

## 3. 불변 조건과 실패 모드

| 조건 | 깨지면 생기는 문제 | 지키는 장치 |
|---|---|---|
| 분류 요청에는 질문만 들어간다 (`messages=[질문]`, system에 과목 없음) | 질문 문구로 분류가 권한 쪽으로 기운다. 게다가 `classify_prompt_hash`는 `classify.md` 파일만 해시하므로, 실행 중에 과목을 끼워 넣으면 해시가 그대로라 평가 기록에 변화가 드러나지 않는다 | `test_classify_sends_only_question_without_role_or_sampling` |
| 라벨 한 단어만 인정 (`parse_intent`) | "academic because …"를 받아 주면 설명이 붙은 출력이 정답으로 집계되고, `classify_max_tokens`를 늘려도 안 드러난다 | `test_parse_intent` |
| 형식 오류·거절은 `both` + `valid=False` | `valid=True`로 두면 의도 정확도가 부풀려진다. `none`으로 두면 답할 수 있는 질문을 거절한다 | `test_classify_garbage_falls_back_to_both_invalid`, `test_intent_ok_requires_valid_label` |
| 처리 표 결과 ∩ MCP 보이는 도구만 호출 | 표가 실수로 미수강자에게 `search_major`를 내줘도 권한 겹이 막는다. 다만 이 교집합 단계를 빼면 그 호출이 "사용할 수 없는 도구" 오류로 돌아와 `tool_error` 공지에 섞이고, 표의 버그가 장애처럼 보인다 | `test_planned_tool_outside_visible_list_is_never_called` |
| 도구 하나가 실패해도 나머지로 답한다 (baseline에도 적용) | 학사 검색 장애 하나로 전공 질문까지 전부 실패 | `test_one_failing_tool_does_not_sink_answer` |
| 도구 실패는 평가에서 세어 보이게 한다 (`tool_errors`, 비교표 "도구 오류") | 실패해도 답변이 나오므로 recall 하락이 장애 탓인지 안 보인다. 모든 도구가 실패해 붙은 `no_evidence`가 none 문항을 "잘 거절함"으로 통과시킨다 | `test_evaluate_item_counts_tool_errors`, `test_none_handled_does_not_credit_decline_caused_by_tool_failure`, `test_report_shows_tool_error_count_so_outages_are_visible` |
| `none`은 학교·학과와 명백히 무관할 때만 (`classify.md` 규칙 3) | 잘못된 none은 검색을 건너뛰어 답을 잃는다(router-v1의 A11 "eval 서버"). 반대로 잘못된 academic은 검색 한 번이 더 들 뿐이다 — 비용이 비대칭이라 망설이면 none이 아닌 쪽으로 보낸다 | 평가의 "라우팅 손실" 열 (`test_routing_loss_counts_only_misroutes_that_lost_the_evidence`) |
| 라우터 효과는 같은 커밋·같은 날의 `baseline-v2`와 비교 | 3주차 baseline은 생성 프롬프트(오늘 날짜 규칙)가 달라 라우터 효과에 프롬프트 변화가 섞인다. 다른 날 재면 마감 관련 답이 달라져 날짜 변수가 섞인다 | 평가 meta의 `prompt_hash`·`commit`·`today`, 비교표 "측정일" 열 |
| `none`·미수강 major는 임베딩·검색·생성 없이 안내만 | 범위 밖 질문에 비용이 들고, 모델이 일반 상식으로 답을 지어낼 여지가 생긴다 | `test_workflow_none_intent_answers_without_search_or_generation`, `test_workflow_none_intent_skips_embedding_and_search`, `test_workflow_major_intent_for_guest_explains_restriction`, `test_workflow_both_intent_for_guest_searches_academic_only_and_explains` |
| `none_handled`가 `out_of_scope` 공지를 거절로 인정 | 라우터가 none을 잘 걸러도 none 처리 지표가 0%로 떨어져 보인다 | `test_none_handled_accepts_out_of_scope` |
| 평가 기록의 `intent`는 정답 라벨, 분류 결과는 `predicted_intent` | 같은 이름에 쓰면 정답이 덮여 의도 정확도를 계산할 수 없다 | `test_evaluate_item_records_prediction_without_overwriting_gold_intent` |
| 평가 `--mode` 기본값은 `baseline` (설정의 `router_mode` 아님) | `.env`의 `ROUTER_MODE`가 바뀌면 같은 명령이 조용히 다른 모드를 잰다 | `evaluation/run.py` argparse |
| "오늘"은 서울 날짜이고 생성 입력 앞에 붙는다 | 서버(EC2, UTC)에서 한국 오전 9시 전 질문의 '오늘'이 하루 밀린다. 파이프라인이 날짜를 안 넘기면 지난 마감을 유효하게 안내한다 | `test_seoul_date_rolls_over_at_15_utc`, `test_pipeline_passes_today_to_generation` |
| MCP 도구의 `query`는 문자열만 | `str(["a"])`·`str(None)`으로 엉뚱한 검색이 실행된다 | `test_non_string_query_is_rejected` |

외부 요인:
- **Haiku 장애·타임아웃:** 지금은 예외가 그대로 올라간다(평가 실행이 멈춤). API의 503 변환과 한도 되돌림은 M3b(`UpstreamError`)에서 처리한다.
- **분류 거절(`stop_reason == "refusal"`):** content를 읽지 않고 `both`·invalid로 처리한다.

## 3-1. 측정 기록과 해석 (2026-10-13)

| 실행 | 답변 정확도 | 의도 정확도 | 라우팅 손실 | recall@5 |
|---|---|---|---|---|
| baseline-v2 | 91.7% | — | — | 90.0% |
| router-v1 | 86.1% | 72.2% | 1 (A11) | 86.7% |

- **의도 정확도가 낮게 나오는 구조적 이유:** 평가셋의 `none`은 "우리 자료에 없음"(기숙사·졸업학점·개강일·주차 등)인데, 분류기는 자료 목록을 모르므로 이 질문들을 의미대로 `academic`으로 분류한다. 이런 오분류는 검색 후 "찾을 수 없다"로 거절되어 피해가 없다(none 처리 100%). 그래서 사용자 피해는 **라우팅 손실**(오분류 + 근거 못 찾음)로 본다.
- **피해 없는 오분류:** 과목 이름이 든 학사 질문 → `both`. 학사 검색이 포함되어 답은 맞고 전공 검색이 한 번 더 돈다 → `classify.md` 규칙 1.
- router-v2부터 `classify.md` 규칙 1~3을 적용했다. 평가셋 36문항에 문장을 맞추지 않고 "비용 비대칭" 원칙만 넣었다(과적합 방지).

## 4. 다음 수정

- **M3b (4~5주차):** `/api/ask`가 `mode=settings.router_mode`로 이 함수를 부른다. 공급사 오류 → `UpstreamError` → 503.
- **측정 (튜터):** 같은 커밋에서 `baseline-v2`와 `router-v1`을 재고 채점한다. 분류 오답 사례는 `classify.md` 수정 후보.
- **7주차:** 검색 실패 문항(M08·M10·M11)은 라우터가 아니라 검색 문제 → 하이브리드 검색.
- **6주차 agent 모드:** `MODES`에 `"agent"`를 더하고, 도구 선택을 모델에 맡긴다. 처리 표의 권한 판단은 MCP 권한 두 겹으로 계속 보장된다.

## 5. 업데이트 시 주의점

- **`classify.md`를 고칠 때는 평가셋 문항을 보며 문장을 맞추지 않는다.** 36문항에 맞춘 규칙은 실제 질문에서 무너진다. 원칙(비용 비대칭, 운영 질문은 academic)만 넣고 라우팅 손실로 확인한다.
- **`classify.md`를 고치면** `classify_prompt_hash`가 바뀐다. 이전 `router-*` 실행과 직접 비교하지 말고 같은 커밋에서 다시 잰다.
- **`answer.md`를 고치면** 생성 프롬프트 해시(`prompt_hash`)가 바뀐다. 라우터 효과 비교용 `baseline-v*`도 같은 커밋·같은 날 다시 잰다.
- **`render_context`(자료·날짜를 붙이는 코드)를 고치면 해시가 바뀌지 않는다** — `prompt_hash`는 `answer.md` 파일만 본다. 모델 입력은 바뀌었는데 기록은 같아 보이므로, 이때도 기준선을 다시 재고 커밋 해시로 구분한다.
- **baseline 모드도 이번 변경으로 달라졌다:** 오늘 날짜 주입, 도구 실패 격리(예전엔 평가가 멈춤 → 이제 `tool_error` 공지와 함께 계속), 질문 앞뒤 공백 제거·빈 질문 `ValueError`. 3주차 `baseline` 수치와 직접 비교하지 않는다.
- **의도 라벨을 추가·변경하면** `INTENTS`, `classify.md`, `plan` 표, `eval/questions.yaml`의 `intent`(동결됨 — 바꾸면 `make eval-freeze` 재실행과 이전 실행 무효), 설계 §5 표를 함께 바꾼다.
- **처리 표를 바꾸면** `test_plan_table`의 8개 경우를 먼저 고친다. 미수강자에게 `search_major`가 나가는 변경은 권한 두 겹이 막더라도 리뷰에서 거절한다.
- **도구 이름(`TOOL_*`)을 바꾸면** 처리 표·평가 기록의 `tool_error:<이름>` 공지·dev-note를 같이 바꾼다.

## 파일 위치

| 파일 | 역할 |
|---|---|
| `backend/app/core/router.py` | `classify`, `parse_intent`, `plan`, `classify_prompt_hash` |
| `backend/app/core/prompts/classify.md` | 분류 시스템 프롬프트 (SoT) |
| `backend/app/core/pipeline.py` | `answer_question(mode=…)`, 도구 실패 격리, 날짜 주입 |
| `backend/app/core/clock.py` | `seoul_today` |
| `backend/evaluation/{metrics,run,report}.py` | `intent_ok`, `--mode`, 비교표 모드·의도 정확도 열 |
