# 로그인·일일 한도·질문 API — M3b

> 마지막 갱신: 2026-10-13 · 계획: [`docs/exec-plans/active/2026-09-30-m3b-auth-api.md`](../exec-plans/active/2026-09-30-m3b-auth-api.md) · 설계 §4

## 1. 핵심 개념

**왜 로그인이 필요한가.** 전공 강의자료는 수강생에게만 보여야 한다(권한 두 겹). 지금까지는 평가 스크립트가 "전 과목 수강생"을 흉내 냈지만, 실제 서비스는 "이 요청을 보낸 학생이 누구고 무엇을 듣는가"를 서버가 확실히 알아야 한다.

**토큰에는 누구인지만, 권한은 DB에서.** JWT에는 `sub`(user_id)·`iat`·`exp`만 넣는다. 수강 과목·한도는 요청마다 `users`·`enrollments`에서 다시 읽는다. 과목을 토큰에 넣으면 수강을 취소해도 토큰이 만료될 때까지(12시간) 옛 권한이 남는다.

**한도는 비용 방어선.** 질문 하나마다 LLM·임베딩 비용이 든다. 일일 한도는 서울 날짜 기준으로 세고, 한 SQL 문장으로 원자 증가한다.

**API는 얇게.** `app/api`는 인증·입력 검증·한도·오류 변환만 한다. 답변은 주입된 `answer_fn`(= `answer_question(mode=ROUTER_MODE)`)이 만든다. 그래서 테스트는 `app.dependency_overrides`로 답변 함수만 바꿔 HTTP 동작을 검증한다.

## 2. 데이터 흐름

```
POST /api/auth/login {username, password}
 → find_user → verify_password(없는 계정도 더미 해시로 검증)
 → issue_token(user_id, JWT_SECRET, 12h) → {access_token, token_type: "bearer"}

POST /api/ask {question}   Authorization: Bearer <token>
 ├ AskRequest 검증: 앞뒤 공백 제거, 1~500자          → 실패 422 (한도 차감 전)
 ├ current_user: decode_token → get_user(삭제 계정이면 401) → user_courses(DB)
 ├ consume_quota(user, 서울 날짜, daily_quota)        → 실패 429 (롤백)
 ├ commit (차감 확정)
 ├ answer_fn(question, UserContext(user_id, courses), session)
 │    └ answer_question: 질문 임베딩을 MCP 도구 전에 먼저 계산 → 도구 → 생성
 │      anthropic/openai APIError → UpstreamError
 ├ UpstreamError → refund_quota + commit → 503
 └ {answer, sources[{file,page,section}], intent, notices}
```

## 3. 불변 조건과 실패 모드

| 조건 | 깨지면 생기는 문제 | 지키는 장치 |
|---|---|---|
| `JWT_SECRET`이 32자 미만이면 발급·검증 모두 거부 | 기본값 `""`로 서명되면 누구나 같은 키로 토큰을 위조해 아무 학생으로 행세한다 | `test_short_secret_is_refused` |
| `decode_token`은 `algorithms=["HS256"]` 고정, `exp`·`sub` 필수 | `alg: none` 토큰이 서명 없이 통과하거나, 만료 없는 영구 토큰이 생긴다 | `test_decode_rejects_missing_sub_and_none_alg`, `test_decode_rejects_expired_token` |
| 토큰에는 user_id만, 과목은 요청마다 DB에서 | 수강 취소·게스트 전환이 토큰 만료 전까지 반영되지 않는다 | `test_token_round_trip_carries_only_user_id`, `test_guest_courses_come_from_db_not_token` |
| 토큰의 계정이 지금 DB에 있어야 한다 | 삭제한 계정의 토큰으로 12시간 동안 계속 질문한다 | `test_ask_rejects_token_of_deleted_user` |
| 없는 계정·틀린 비밀번호는 같은 401·같은 문구·같은 검증 비용 | 응답 문구나 시간 차이로 어떤 아이디가 존재하는지 알아낼 수 있다 | `test_login_failures_are_indistinguishable`, `verify_password`의 더미 해시 |
| 입력 검증(422) → 한도(429) → 답변 순서 | 빈 질문·500자 초과 질문에도 한도가 깎인다 | `test_invalid_question_does_not_consume_quota` |
| 한도 증가는 `INSERT … ON CONFLICT … WHERE count < limit` 한 문장 | 읽고-비교하고-쓰면 동시 요청이 같은 값을 읽어 한도를 넘긴다 | `test_consume_stops_at_limit` |
| 0 한도는 코드에서 먼저 거부 | 첫 INSERT는 WHERE를 거치지 않아 0 한도 계정도 하루 1번 통과한다 | `test_zero_quota_never_consumes` |
| 공급사 장애(503)일 때만 한도를 되돌린다 | 장애로 답을 못 받은 학생이 한도를 잃거나(되돌리지 않음), 4xx까지 되돌리면 잘못된 요청으로 무한 재시도가 가능하다 | `test_upstream_error_refunds_quota` |
| 질문 임베딩은 MCP 도구 호출 전에 계산 | 임베딩 장애가 도구 안에서 `tool_error`로 삼켜져 "자료 없음" 답이 나가고, 503이 아니라서 한도도 되돌려지지 않는다 | `test_embedding_failure_surfaces_instead_of_becoming_no_evidence` |
| 비밀번호는 getpass·`--password-stdin`으로만 | argv에 넣으면 셸 기록·프로세스 목록에 남는다 | `test_password_cannot_be_passed_as_argument` |
| `upsert_user`는 과목을 통째로 교체 | 빠진 과목의 `enrollments` 행이 남아 수강 취소 과목의 전공 자료가 계속 보인다 | `test_upsert_replaces_courses_and_password` |
| 한도 날짜는 서울 기준 | 서버(UTC)에서 한국 오전 9시에 한도가 초기화된다 | `seoul_today`, `test_seoul_date_rolls_over_at_15_utc` |

외부 요인:
- **DB 연결 끊김:** 처리하지 않는다(500). 한도 차감 전이면 손해 없음, 차감 후 답변 중이면 한도 1회가 소모된다.
- **답변 함수의 그 밖의 예외(버그):** 500이며 한도를 되돌리지 않는다. 되돌리면 버그를 반복 호출로 우회할 수 있다.

## 4. 다음 수정

- **M4 (5주차) 화면:** 프론트가 `sessionStorage`에 토큰을 두고 `Authorization: Bearer`로 보낸다. 401이면 로그인 화면으로.
- **배포:** EC2의 `.env`에 `JWT_SECRET`(예: `python -c "import secrets; print(secrets.token_urlsafe(48))"`)을 넣는다. 비면 로그인이 전부 실패한다(의도된 동작).
- **로그인 시도 제한:** 아직 없다. 공개 배포 전에 IP·계정별 실패 횟수 제한을 검토한다.
- **로그:** 요청 로그(JSON 한 줄)는 로깅 모듈을 만들 때 추가한다(AGENTS.md "로그").

## 5. 업데이트 시 주의점

- **라우트를 바꾸면** `make generate`로 `docs/generated/openapi.json`을 갱신해 같은 커밋에 넣는다(게이트 1 스냅샷 테스트).
- **`ask`의 순서(검증 → 차감 → 커밋 → 답변 → 503 되돌림)를 바꾸지 않는다.** 차감 커밋을 답변 뒤로 미루면 답변이 도는 동안 같은 학생의 동시 요청이 한도를 넘는다.
- **새 공급사 오류 타입**(예: 다른 임베딩 공급사)을 쓰면 `get_answer_fn`의 `except`에 추가해야 503·되돌림이 동작한다.
- **`backend/app/api/`, `backend/app/core/security.py`는 위험 경로**다 — 바꾸면 게이트 3(교차 모델 리뷰).
- **토큰 payload에 필드를 추가하지 않는다.** 필요한 정보는 `current_user`에서 DB로 읽는다.

## 파일 위치

| 파일 | 역할 |
|---|---|
| `backend/app/api/routes.py` | `/api/auth/login`, `/api/ask`, 요청·응답 모델 |
| `backend/app/api/deps.py` | 세션, `current_user`, `get_answer_fn`(공급사 오류 → `UpstreamError`) |
| `backend/app/core/security.py` | argon2 비밀번호, HS256 토큰 |
| `backend/app/core/users.py` | `make users` 계정 CLI |
| `backend/app/db/accounts.py`, `usage.py` | 계정·수강 저장소, 원자 한도 |
