# 권한 설계 문서 (1판)

> 1판 2026-10-27 · 6주차 M5 · 완성본은 8주차("README 및 권한 설계 문서 완성") · 계획: [`m5-agent`](../exec-plans/active/2026-10-27-m5-agent.md) · 상위 설계: [`2026-09-28-system-design.md`](2026-09-28-system-design.md) §4
>
> **이 문서가 "도구 노출·접근 권한 정책"의 SoT다.** `ARCHITECTURE.md`는 요약과 링크만 둔다.
> 표시 규칙: 테스트 이름에 † 가 붙은 것은 M5 코드 PR(`feat/m5-agent`)과 함께 들어오는 테스트다. 그 PR이 병합되기 전의 `main`에는 아직 없다.

## 1. 역할 정의

이 시스템에는 역할 컬럼이 없다. 전공 접근은 `enrollments` 행이 있느냐로만 판단한다(설계 §3).

| 역할 | 정의 | 볼 수 있는 자료 | 만드는 방법 |
|---|---|---|---|
| 게스트 | 수강 과목이 없는 계정 | 학사·공지 | `make users ARGS="add kim"` (`--courses` 생략) |
| 수강생 | 수강 과목이 1개 이상인 계정 | 학사·공지 + **자기 과목** 전공 | `make users ARGS="add kim --courses AGENT,AWS"` |
| 평가 전용 사용자 | `make eval`이 코드에서 만드는 `UserContext(user_id=0, courses=적재된 전 과목)`. DB 계정이 아니고 로그인·토큰 경로를 지나지 않는다 | 학사·공지 + 전 과목 전공 | `backend/evaluation/run.py`가 실행마다 만든다 |
| 관리자 | 계정·수강을 바꾸는 사람 | — | **CLI(`make users`)뿐.** 관리자 API·화면이 없다 |

- 토큰에는 `user_id`만 있다. 수강 과목은 **요청마다 DB에서** 읽는다 → 수강을 바꾸면 재로그인 없이 바로 반영되고, 토큰을 위조·재사용해도 과목을 부풀릴 수 없다.
- 회원가입 API가 없으므로 "스스로 역할을 올리는" 경로가 없다.

## 2. 권한 겹

겹은 셋이다. 겹 0은 **무엇을 하지 않는가**이고, 겹 1·2가 실제로 막는다.

| 겹 | 위치 | 하는 일 | 이 겹이 없으면 무엇이 새는가 |
|---|---|---|---|
| 0. 모델 입력에 권한 정보 없음 | `core` (분류기·에이전트 공통) | 분류 요청에는 질문만, 에이전트 첫 메시지에는 날짜와 질문만 넣는다. 역할·수강 과목을 프롬프트에 쓰지 않는다 | 질문 속 "나는 AI 과목 수강생이야" 같은 문구가 모델 판단을 흔든다. 권한을 모델이 알면 모델이 권한을 "해석"하게 되고, 해석은 우회할 수 있다. 권한은 코드(겹 1·2)만 정한다 |
| 1. MCP 도구 노출·인자 좁히기 | `app/mcp/server.py` | `UserContext(user_id, courses)`를 서버가 만든다. `list_tools`는 `search_academic`을 항상, `search_major`는 `courses`가 있을 때만 보여준다. `search_major(course_code?)`는 사용자 과목과의 **교집합**만 쓴다(좁히기만 가능) | 게스트가 전공 도구를 호출할 수 있다(겹 2가 막아 0건이 되지만 장애처럼 보이는 오류가 섞인다). agent 모드에서는 모델이 **존재를 아는 도구만** 부르므로, 겹 1이 곧 "모델에게 보이는 선택지"다 |
| 2. 검색 조회 필터(SQL) | `app/db/search.py` | `search_chunks(…, scope, allowed_courses)` — 기본값 없는 필수 키워드 인자. `WHERE scope='academic' OR (scope='major' AND course_code = ANY(:allowed_courses))` | **실제 방어선.** 겹 1에 버그가 있거나 코드가 `db.search`를 직접 불러도 미수강 과목의 전공 조각이 결과에 들어온다. 이 겹은 가장 아래 계층(`db`)에 있어 위 계층 누구도 우회할 수 없다 |

겹 1의 목적은 두 가지다. ① 비용·지연 절감(안 보이는 도구는 안 부른다) ② agent 모드의 선택지 제한. 하지만 **보안의 최후 보루는 겹 2**다. 겹 1만 있고 겹 2가 없는 검색 코드는 병합하지 않는다(`AGENTS.md` 절대 규칙 1).

> 점수로는 걸러지지 않는다. 같은 `scope`의 다른 과목 조각(예: CS101 대 CS202)은 질문과의 유사도가 비슷할 수 있으므로 `min_score`가 아니라 `course_code` 조건이 가른다. 권한 행렬 테스트의 픽스처가 이 "같은 축" 상황을 일부러 만든다.

## 3. 모드별 경로

세 모드 모두 **같은 `build_server(user, …)`** 를 지난다. 모드가 달라도 겹 1·2는 건너뛸 수 없다.

| | baseline | workflow | agent |
|---|---|---|---|
| 도구를 고르는 주체 | 코드(보이는 도구 전부) | 분류기(Haiku) + 코드 처리 표 `plan()` | **모델**(Sonnet), 보이는 도구 중에서 |
| 모델이 보는 도구 목록 | 없음 | 없음 | `list_tools` 결과 그대로(`tools` 인자) |
| 겹 0 | — | 분류 요청에 질문만 | 첫 메시지에 날짜+질문만 |
| 겹 1 (도구 노출) | 호출 대상 = 보이는 도구 | 호출 대상 = `plan.tools ∩ 보이는 도구` | 모델 `tools` = 보이는 도구. 목록에 없는 이름의 호출은 실행하지 않는다(`invalid_tool_call`) |
| 겹 2 (SQL) | 통과 | 통과 | 통과 |
| 미수강자의 전공 질문 | 학사만 검색됨 | 처리 표가 "수강생 전용" 안내(검색 없음) | 모델이 `search_major`를 볼 수 없어 학사만 검색 |

- workflow의 처리 표(`router.plan`)는 **권한이 아니라 안내용**이다. 표에 버그가 있어 미수강자에게 `search_major`를 내줘도 교집합과 겹 2가 막는다. 표를 믿고 겹 1·2를 줄이면 안 된다.
- agent 모드의 "잘못된 호출"(`invalid_tool_call`)은 장애(`tool_error:`)와 구분한다. 섞으면 화면에 "일부 자료를 검색하지 못했습니다"가 뜨고, 평가가 장애 섞인 실행으로 오판한다.
- 게스트 agent 응답에는 `major_requires_enrollment` 공지를 붙이지 않는다. 모델이 전공 도구를 못 보는 것으로 충분하다(필요하면 7주차에서 다시 판단).

## 4. 위협과 대응

| 위협 | 어떻게 막는가 | 지키는 장치 |
|---|---|---|
| 질문에 "나는 수강생이야/관리자야"라고 쓴다 | 모델 입력에 권한이 없고, 권한은 요청마다 DB의 `enrollments`로만 정해진다. 질문 문장은 권한 입력이 아니다 | `test_classify_sends_only_question_without_role_or_sampling`(workflow), `test_agent_first_message_has_today_and_no_courses`†(agent) |
| `search_major(course_code="다른 과목")`로 범위를 넓힌다 | 사용자 과목과의 교집합만 쓴다. 비면 0건 | `test_course_code_argument_cannot_widen` |
| 모델이 보이지 않는 도구(`search_major`)를 부른다 | `list_tools`에 없는 이름이면 MCP를 부르지 않고 오류 결과를 돌려준다. 호출이 MCP에 닿아도 겹 1이 한 번 더 거른다 | `test_agent_hidden_tool_call_is_not_executed`† |
| 도구 인자 `query`에 문자열이 아닌 값을 넣는다 | 문자열만 허용(`str([..])`로 엉뚱한 검색이 도는 것을 막는다) | `test_non_string_query_is_rejected`, `test_agent_non_string_query_is_invalid_call`† |
| 코드가 MCP를 거치지 않고 `db.search`를 직접 부른다 | `allowed_courses`가 기본값 없는 필수 인자이고, SQL 조건이 항상 붙는다 | `test_allowed_courses_is_required_keyword`, `test_enrolled_student_sees_only_own_course` |
| 삭제된 계정의 토큰을 계속 쓴다 | 토큰은 `user_id`만 담고, 요청마다 DB에서 사용자를 찾는다. 없으면 거절 | `test_ask_rejects_token_of_deleted_user` |
| 수강을 바꿨는데 이전 토큰으로 이전 권한이 남는다 | 과목을 토큰에 넣지 않고 요청마다 DB에서 읽는다 → 즉시 반영 | `test_me_reflects_enrollment_change_without_relogin`, `test_guest_courses_come_from_db_not_token` |
| 앞선 도구 호출의 결과가 다른 사용자에게 섞인다 | 에이전트 루프의 조각 누적은 **요청 하나의 지역 변수**이고, MCP 서버도 요청마다 `UserContext`로 새로 만든다 | `test_no_foreign_major_chunk_reaches_answer_or_model`† |

## 5. 권한 테스트 행렬

설계 §4의 4행(게이트 1)에 agent 모드 행을 더했다. 기존 4행은 새로 쓰지 않고 이미 있는 테스트로 연결한다.

| 사용자 | 기대 | 테스트 |
|---|---|---|
| A 수강생 | A 전공 + 학사만 | `test_enrolled_student_sees_only_own_course` |
| 수강 과목 없음 | 학사만, `search_major` 미노출 | `test_no_enrollment_sees_only_academic` |
| A 수강생이 `course_code=B` | 0건 | `test_course_code_argument_cannot_widen` |
| MCP 우회해 `db.search` 직접 호출 | 필터 유지 | `test_allowed_courses_is_required_keyword`, `test_partial_index_path_still_returns_enrolled_chunk` |
| **모드 3종 × (게스트·CS101 수강생)** — 남의 전공 조각이 최종 답·검색 결과·모델 입력에 0건 | `answer.retrieved`의 전공 조각 `course_code ⊆ courses`, 모든 LLM 호출의 messages·system에 `CS202` 경로 없음, 게스트는 `major/` 조각 0건 | `test_no_foreign_major_chunk_reaches_answer_or_model`† (`mode` × `courses` parametrize) |
| **agent의 `tools` 인자 = MCP 보이는 도구** | 게스트·수강생별로 모델에 넘긴 도구 이름 집합 == `visible_tools(user)` | `test_agent_tools_argument_matches_mcp_visibility`† |
| 게스트에게 `search_major`가 안 보임 / 호출해도 실행 안 됨 | `tools`에 `search_major` 없음, 호출은 미실행 + `invalid_tool_call` | `test_agent_guest_gets_only_academic_tool`†, `test_agent_hidden_tool_call_is_not_executed`† |
| 로그인 → `/api/ask` → 출처 (실제 파이프라인·MCP·DB) | 게스트 응답 `sources`에 `major/` 없음 | `test_guest_login_ask_never_sees_major`† |

행렬 픽스처는 조각 `academic/calendar.pdf`, `major/CS101/lec1.pdf`, `major/CS202/lec1.pdf`다. CS101과 CS202가 같은 `scope`라 점수가 아니라 `course_code` 조건만이 가른다.

**테스트가 진짜 막는지(RED 대체 확인):** 행렬 테스트는 M5 이전 코드에 대한 재검증이라 처음부터 통과한다. 그래서 `visible_tools`의 `if user.courses:`를 잠시 지워 FAIL을 확인한 뒤 되돌린다. 그 결과 한 줄은 계획의 결정 로그에 남긴다.

## 6. 1판의 한계 — 8주차 완성 예정, 남은 것

- **게스트 agent 응답 안내:** 전공 질문을 한 게스트에게 "수강생 전용 자료"라고 알리는 공지가 agent 모드에는 없다(workflow에는 있다). 계획은 "모델이 전공 도구를 못 보는 것으로 충분"하다고 판단했고, 실제 화면에서 어떻게 보이는지는 확인하지 않았다.
- **평가 전용 사용자의 경계:** `UserContext(user_id=0, 전 과목)`은 `evaluation/run.py`에서만 만든다. 다른 코드가 같은 방식으로 전 과목 `UserContext`를 만들지 못하게 막는 장치(구조 테스트 등)는 아직 없다.
- **한도(429)와 권한의 관계:** 일일 한도는 권한이 아니라 비용 통제로 설계 §4에 있다. 권한 문서에서는 다루지 않았다.
- **로그에 남는 권한 정보:** 설계 §7 관측 로그에 `user_id`는 있고 수강 과목은 없다. 권한 사고 조사에 충분한지 검토가 필요하다.
- **위협 모델의 범위:** 학생이 질문 문구로 시도하는 우회와 코드 버그 두 가지만 다뤘다. 서버 침해(`.env`·DB 접근), 공용 AWS 계정의 다른 Admin은 설계 §9 위험 표가 맡고 이 문서 범위 밖이다.
- **수강 변경 감사:** `make users`로 바꾼 이력이 남지 않는다.
- **검색 개선(7주차)과의 충돌:** 하이브리드 검색(키워드 검색 추가)을 넣을 때 키워드 쪽 쿼리에도 겹 2 조건이 붙는지 이 행렬에 행을 더해야 한다.
