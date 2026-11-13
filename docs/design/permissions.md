# 권한 설계 문서 (완성본)

> 완성본 2026-11-11 · 8주차 M6("README 및 권한 설계 문서 완성") · 1판 2026-10-27(6주차 M5) · 계획: [`m6-final-docs`](../exec-plans/active/2026-11-11-m6-final-docs.md), [`m5-agent`](../exec-plans/active/2026-10-27-m5-agent.md) · 상위 설계: [`2026-09-28-system-design.md`](2026-09-28-system-design.md) §4 · 배포: [`dev-notes/deploy.md`](../dev-notes/deploy.md)
>
> **이 문서가 "도구 노출·접근 권한 정책"의 SoT다.** `ARCHITECTURE.md`는 요약과 링크만 둔다.
> 여기 적힌 테스트 이름은 모두 `backend/tests`에 실제로 있다 — `tests/structural/test_docs_final.py`가 검사한다.
> 1판 → 완성본: M5 병합으로  표시 제거, 합쳐진 테스트 이름 정정(§4·§5), §6 배포 서버에서의 권한 추가, 남은 한계를 §7로 갱신.
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
- 게스트 agent 응답에는 `major_requires_enrollment` 공지를 붙이지 않는다. 모델이 전공 도구를 못 보는 것으로 충분하다(§7 남은 한계).

## 4. 위협과 대응

| 위협 | 어떻게 막는가 | 지키는 장치 |
|---|---|---|
| 질문에 "나는 수강생이야/관리자야"라고 쓴다 | 모델 입력에 권한이 없고, 권한은 요청마다 DB의 `enrollments`로만 정해진다. 질문 문장은 권한 입력이 아니다 | `test_classify_sends_only_question_without_role_or_sampling`(workflow), `test_agent_first_message_has_today_and_no_courses`(agent) |
| `search_major(course_code="다른 과목")`로 범위를 넓힌다 | 사용자 과목과의 교집합만 쓴다. 비면 0건 | `test_course_code_argument_cannot_widen` |
| 모델이 보이지 않는 도구(`search_major`)를 부른다 | `list_tools`에 없는 이름이면 MCP를 부르지 않고 오류 결과를 돌려준다. 호출이 MCP에 닿아도 겹 1이 한 번 더 거른다 | `test_agent_invalid_call_is_not_executed`, `test_hidden_tool_call_is_rejected` |
| 도구 인자 `query`에 문자열이 아닌 값을 넣는다 | 문자열만 허용(`str([..])`로 엉뚱한 검색이 도는 것을 막는다) | `test_non_string_query_is_rejected`, `test_agent_invalid_call_is_not_executed` |
| 코드가 MCP를 거치지 않고 `db.search`를 직접 부른다 | `allowed_courses`가 기본값 없는 필수 인자이고, SQL 조건이 항상 붙는다 | `test_allowed_courses_is_required_keyword`, `test_enrolled_student_sees_only_own_course` |
| 삭제된 계정의 토큰을 계속 쓴다 | 토큰은 `user_id`만 담고, 요청마다 DB에서 사용자를 찾는다. 없으면 거절 | `test_ask_rejects_token_of_deleted_user` |
| 수강을 바꿨는데 이전 토큰으로 이전 권한이 남는다 | 과목을 토큰에 넣지 않고 요청마다 DB에서 읽는다 → 즉시 반영 | `test_me_reflects_enrollment_change_without_relogin`, `test_guest_courses_come_from_db_not_token` |
| 앞선 도구 호출의 결과가 다른 사용자에게 섞인다 | 에이전트 루프의 조각 누적은 **요청 하나의 지역 변수**이고, MCP 서버도 요청마다 `UserContext`로 새로 만든다 | `test_no_foreign_major_chunk_reaches_answer_or_model` |

## 5. 권한 테스트 행렬

설계 §4의 4행(게이트 1)에 agent 모드 행을 더했다. 기존 4행은 새로 쓰지 않고 이미 있는 테스트로 연결한다.

| 사용자 | 기대 | 테스트 |
|---|---|---|
| A 수강생 | A 전공 + 학사만 | `test_enrolled_student_sees_only_own_course` |
| 수강 과목 없음 | 학사만, `search_major` 미노출 | `test_no_enrollment_sees_only_academic` |
| A 수강생이 `course_code=B` | 0건 | `test_course_code_argument_cannot_widen` |
| MCP 우회해 `db.search` 직접 호출 | 필터 유지 | `test_allowed_courses_is_required_keyword`, `test_partial_index_path_still_returns_enrolled_chunk` |
| **모드 3종 × (게스트·CS101 수강생)** — 남의 전공 조각이 최종 답·검색 결과·모델 입력에 0건 | `answer.retrieved`의 전공 조각 `course_code ⊆ courses`, 모든 LLM 호출의 messages·system에 `CS202` 경로 없음, 게스트는 `major/` 조각 0건 | `test_no_foreign_major_chunk_reaches_answer_or_model` (`mode` × `courses` parametrize) |
| **agent의 `tools` 인자 = MCP 보이는 도구** | 게스트·수강생별로 모델에 넘긴 도구 이름 집합 == `visible_tools(user)` | `test_agent_tools_argument_matches_mcp_visibility` |
| 게스트에게 `search_major`가 안 보임 / 호출해도 실행 안 됨 | `tools`에 `search_major` 없음, 호출은 미실행 + `invalid_tool_call` | `test_agent_guest_gets_only_academic_tool`, `test_agent_invalid_call_is_not_executed`, `test_hidden_tool_call_is_rejected` |
| 로그인 → `/api/ask` → 출처 (실제 파이프라인·MCP·DB) | 게스트 응답 `sources`에 `major/` 없음 | `test_guest_login_ask_never_sees_major` |

행렬 픽스처는 조각 `academic/calendar.pdf`, `major/CS101/lec1.pdf`, `major/CS202/lec1.pdf`다. CS101과 CS202가 같은 `scope`라 점수가 아니라 `course_code` 조건만이 가른다.

**테스트가 진짜 막는지(RED 대체 확인):** 행렬 테스트는 M5 이전 코드에 대한 재검증이라 처음부터 통과한다. 그래서 `visible_tools`의 `if user.courses:`를 잠시 지워 FAIL을 확인한 뒤 되돌린다. 게이트 2에서 이 변이로 FAIL을 확인했고 계획의 결정 로그에 남겼다.

## 6. 배포 서버에서의 권한 (7주차 M4b)

공개 서버에서는 권한 두 겹(§2) 앞에 **"어디로 들어올 수 있는가"** 가 한 겹 더 생긴다. 사실의 원본은 [`dev-notes/deploy.md`](../dev-notes/deploy.md) §3이고, 여기서는 권한과 이어지는 것만 적는다.

| 경계 | 정책 | 이것이 무너지면 권한에서 무엇이 새는가 | 지키는 장치 |
|---|---|---|---|
| 입구 | 인터넷에 여는 문은 Caddy(80·443)뿐. 앱 8000·DB 5432는 포트를 공개하지 않는다 | DB에 직접 붙으면 겹 1·2를 모두 건너뛰고 전 과목 조각을 읽는다 | `test_only_caddy_publishes_ports`, `test_security_group_exposes_only_web_to_the_world` |
| 접속자 IP | 앱은 Caddy 고정 주소가 전한 IP만 믿는다 | 위조 헤더로 로그인 시도 제한을 피해 계정 비밀번호를 대입한다 | `test_app_trusts_only_caddy_for_forwarded_headers` |
| 비밀값 | `JWT_SECRET`·`DB_PASSWORD`는 서버에서 처음 한 번 생성해 서버 `.env`에만 둔다. 이미지·git에 없다 | `JWT_SECRET`을 알면 아무 `user_id`의 토큰을 만들 수 있다(과목은 DB에서 읽으므로 부풀릴 수는 없지만 남의 계정이 된다) | `infra/deploy.sh`의 생성·덮어쓰기 금지, `test_dockerignore_excludes_secrets_and_data` |
| 계정 | 회원가입 API 없음. 계정·수강은 서버에서 관리자가 CLI로만 만든다. 로컬 `users`는 서버로 옮기지 않는다 | 로컬 시험 계정이 공개 서버에서 살아난다 | `infra/restore-index.sh`(`documents`·`chunks`만 복사) |
| 인스턴스 자격 증명 | 메타데이터 홉 제한 1 | 앱이 뚫리면 컨테이너에서 AWS 자격 증명까지 가져간다 | `test_instance_blocks_container_access_to_role_credentials` |

- 서버는 평소 정지하고 테스트·시연할 때만 켠다. 정지 중에는 접속 자체가 없으므로 권한 경로도 없다. 켤 때는 같은 이미지·같은 `.env`로 다시 시작한다.
- 2026-11-07 외부 접속 테스트(수강생·게스트 계정, 질문 5개)에서 게스트는 전공 질문에 "수강생 전용" 안내만 받고 전공 자료를 받지 못했다. 수강생은 수강 과목 자료로 답을 받았다.

## 7. 남은 한계

- **게스트 agent 응답 안내:** 전공 질문을 한 게스트에게 "수강생 전용 자료"라고 알리는 공지가 agent 모드에는 없다(workflow에는 있다). 모델이 전공 도구를 못 보는 것으로 막히지만, agent 모드 화면에서 게스트가 이유를 알 수 있는지는 아직 확인하지 않았다.
- **평가 전용 사용자의 경계:** `UserContext(user_id=0, 전 과목)`은 `evaluation/run.py`에서만 만든다. 다른 코드가 같은 방식으로 전 과목 `UserContext`를 만들지 못하게 막는 구조 테스트는 아직 없다.
- **한도(429)와 권한의 관계:** 일일 한도는 권한이 아니라 비용 통제로 설계 §4에 있다. 권한 문서에서는 다루지 않는다.
- **로그에 남는 권한 정보:** 관측 로그에 `user_id`는 있고 수강 과목은 없다. 권한 사고 조사에 충분한지 검토가 필요하다.
- **수강 변경 감사:** CLI로 바꾼 계정·수강 이력이 남지 않는다.
- **서버 백업:** DB 볼륨이 인스턴스에 하나뿐이다. 인스턴스를 잃으면 계정·수강 정보가 함께 사라진다(`dev-notes/deploy.md` §4).
- **검색 개선과의 충돌:** 7주차 분석에서 나온 단어 검색 병행(하이브리드)을 넣을 때, 키워드 쪽 쿼리에도 겹 2 조건이 붙는지 §5 행렬에 행을 더해야 한다.
