# 로그인·일일 한도·질문 API — M3b

> 마지막 갱신: 2026-10-13 · 계획: [`docs/exec-plans/done/2026-09-30-m3b-auth-api.md`](../exec-plans/done/2026-09-30-m3b-auth-api.md) · 설계 §4

## 1. 핵심 개념

**왜 로그인이 필요한가.** 전공 강의자료는 수강생에게만 보여야 한다(권한 두 겹). 지금까지는 평가 스크립트가 "전 과목 수강생"을 흉내 냈지만, 실제 서비스는 "이 요청을 보낸 학생이 누구고 무엇을 듣는가"를 서버가 확실히 알아야 한다.

**토큰에는 누구인지만, 권한은 DB에서.** JWT에는 `sub`(user_id)·`iat`·`exp`만 넣는다. 수강 과목·한도는 요청마다 `users`·`enrollments`에서 다시 읽는다. 과목을 토큰에 넣으면 수강을 취소해도 토큰이 만료될 때까지(12시간) 옛 권한이 남는다.

**한도는 비용 방어선.** 질문 하나마다 LLM·임베딩 비용이 든다. 일일 한도는 서울 날짜 기준으로 세고, 한 SQL 문장으로 원자 증가한다.

**API는 얇게.** `app/api`는 인증·입력 검증·한도·오류 변환만 한다. 답변은 주입된 `answer_fn`(= `answer_question(mode=ROUTER_MODE)`)이 만든다. 그래서 테스트는 `app.dependency_overrides`로 답변 함수만 바꿔 HTTP 동작을 검증한다.

## 2. 데이터 흐름

```
POST /api/auth/login {username ≤64자, password ≤256자}       → 길이 초과 422
 → JWT_SECRET 32자 미만이면 503 (비밀번호 확인 전에 멈춤)
 → try_acquire: (IP, 아이디) 15분 5회·IP 15분 20회 안이면 시도 1회를 먼저 기록, 넘으면 429
 → find_user → verify_password(없는 계정도 더미 해시로 검증) → 401 / 성공 시 그 계정 기록 삭제
 → issue_token(user_id, JWT_SECRET, 12h) → {access_token, token_type: "bearer"}

POST /api/ask {question}   Authorization: Bearer <token>
 ├ current_user: JWT_SECRET 확인(503) → decode_token → get_user(삭제 계정이면 401) → user_courses(DB)
 │   (FastAPI는 의존성을 본문 검증보다 먼저 푼다 — 토큰이 틀리면 질문이 비어도 401)
 ├ AskRequest 검증: 앞뒤 공백 제거, 1~500자          → 실패 422 (한도 차감 전)
 ├ consume_quota(user, 서울 날짜, daily_quota)        → 실패 429 (롤백)
 ├ commit (차감 확정)
 ├ answer_fn(question, UserContext(user_id, courses), session)
 │    └ answer_question: 질문 임베딩을 MCP 도구 전에 먼저 계산 → 도구 → 생성
 │      공급사 연결 실패·시간 초과·5xx·429 → UpstreamError (4xx는 그대로 500)
 ├ UpstreamError → rollback → refund_quota + commit → 503
 └ {answer, sources[{file,page,section}], intent, notices}
```

## 3. 불변 조건과 실패 모드

| 조건 | 깨지면 생기는 문제 | 지키는 장치 |
|---|---|---|
| `JWT_SECRET`이 32자 미만이면 발급·검증 모두 거부 | 기본값 `""`로 서명되면 누구나 같은 키로 토큰을 위조해 아무 학생으로 행세한다 | `test_short_secret_is_refused` |
| 키가 없을 때는 비밀번호 확인 전에 같은 503 | 맞는 비밀번호만 500(토큰 발급 실패)이 나면 비밀번호 정답 여부가 새어 나가 무차별 대입 오라클이 된다 | `test_missing_jwt_secret_does_not_reveal_password_correctness` |
| (IP, 아이디)별 15분 5회·IP별 20회를 넘으면 맞는 비밀번호도 429 | 제한이 없으면 비밀번호를 무한히 맞혀 볼 수 있다. 아이디만 키로 쓰면 남의 계정을 일부러 잠글 수 있고, IP 상한이 없으면 아이디를 바꿔 가며 뿌릴 수 있다 | `test_repeated_login_failures_are_throttled_per_ip_and_username`, `test_one_ip_cannot_spray_many_usernames`, `test_block_lifts_after_window` |
| 시도는 확인과 같은 잠금 안에서 **먼저** 기록(`try_acquire`) | 확인하고 실패를 나중에 기록하면 동시에 들어온 요청이 모두 확인을 통과해 제한을 넘는다 | `test_concurrent_attempts_cannot_exceed_limit` |
| 제한 기록 수는 `max_keys`로 묶되, 창 안의 기록은 지우지 않고 꽉 차면 새 조합을 429로 거절 | 상한이 없으면 임의 조합으로 메모리를 계속 늘린다. 반대로 오래된 기록부터 지우면 공격자가 새 조합을 쏟아부어 자기 차단 기록을 밀어내 제한을 초기화한다(대신 대량 IP 공격 중에는 정상 사용자도 잠시 429) | `test_memory_is_bounded_and_full_table_fails_closed`, `test_flooding_new_keys_cannot_evict_a_blocked_record` |
| 로그인 입력 길이 상한(아이디 64·비밀번호 256) | 아주 긴 비밀번호로 argon2 해싱 부하를 줘 서버를 붙잡을 수 있다 | `test_login_input_length_is_limited` |
| `decode_token`은 `algorithms=["HS256"]` 고정, `exp`·`sub` 필수 | `alg: none` 토큰이 서명 없이 통과하거나, 만료 없는 영구 토큰이 생긴다 | `test_decode_rejects_missing_sub_and_none_alg`, `test_decode_rejects_expired_token` |
| 토큰에는 user_id만, 과목은 요청마다 DB에서 | 수강 취소·게스트 전환이 토큰 만료 전까지 반영되지 않는다 | `test_token_round_trip_carries_only_user_id`, `test_guest_courses_come_from_db_not_token` |
| 토큰의 계정이 지금 DB에 있어야 한다 | 삭제한 계정의 토큰으로 12시간 동안 계속 질문한다 | `test_ask_rejects_token_of_deleted_user` |
| 없는 계정·틀린 비밀번호는 같은 401·같은 문구·같은 검증 비용 | 응답 문구나 시간 차이로 어떤 아이디가 존재하는지 알아낼 수 있다. 더미 해시를 첫 호출 때 만들면 기동 뒤 첫 요청만 느려진다 | `test_login_failures_are_indistinguishable`, 모듈 로딩 때 만드는 `_DUMMY_HASH` |
| 입력 검증(422) → 한도(429) → 답변 순서 | 빈 질문·500자 초과 질문에도 한도가 깎인다 | `test_invalid_question_does_not_consume_quota` |
| 한도 증가는 `INSERT … ON CONFLICT … WHERE count < limit` 한 문장 | 읽고-비교하고-쓰면 동시 요청이 같은 값을 읽어 한도를 넘긴다 | `test_consume_stops_at_limit`, `test_concurrent_requests_cannot_exceed_limit` |
| 0 한도는 코드에서 먼저 거부 | 첫 INSERT는 WHERE를 거치지 않아 0 한도 계정도 하루 1번 통과한다 | `test_zero_quota_never_consumes` |
| 공급사 장애(연결 실패·시간 초과·5xx·429)일 때만 503과 한도 되돌림 | 장애로 답을 못 받은 학생이 한도를 잃는다. 반대로 공급사 4xx(잘못된 요청·인증)까지 되돌리면 생성에서 400이 나는 질문을 한도 소모 없이 반복해 분류 비용만 쌓을 수 있다 | `test_upstream_error_refunds_quota`, `test_provider_outage_becomes_upstream_error`, `test_provider_client_error_is_not_treated_as_outage` |
| 질문 임베딩은 MCP 도구 호출 전에 계산 | 임베딩 장애가 도구 안에서 `tool_error`로 삼켜져 "자료 없음" 답이 나가고, 503이 아니라서 한도도 되돌려지지 않는다. (평가 실행은 이제 임베딩 장애에서 멈춘다 — 장애가 섞인 측정을 남기지 않는 쪽) | `test_embedding_failure_surfaces_instead_of_becoming_no_evidence` |
| 비밀번호 옵션은 약어를 받지 않는다(`allow_abbrev=False`) | `--password`가 `--password-stdin`으로 해석돼 사용자가 비밀번호를 인자로 넘겼다고 착각한다 | `test_password_option_prefix_is_not_accepted_as_abbreviation` |
| 비밀번호는 getpass·`--password-stdin`으로만 | argv에 넣으면 셸 기록·프로세스 목록에 남는다 | `test_password_cannot_be_passed_as_argument` |
| `upsert_user`는 과목을 통째로 교체 | 빠진 과목의 `enrollments` 행이 남아 수강 취소 과목의 전공 자료가 계속 보인다 | `test_upsert_replaces_courses_and_password` |
| `GET /api/me`는 과목을 DB에서 읽고 한도를 차감하지 않는다 | 화면 배지가 옛 수강 정보를 보여 학생이 왜 전공 답이 안 나오는지 모르고, 화면을 열 때마다 한도가 깎인다 | `test_me_reflects_enrollment_change_without_relogin`, `test_me_does_not_consume_quota` |
| 한도 날짜는 서울 기준 | 서버(UTC)에서 한국 오전 9시에 한도가 초기화된다 | `seoul_today`, `test_seoul_date_rolls_over_at_15_utc` |

외부 요인:
- **DB 연결 끊김:** 처리하지 않는다(500). 한도 차감 전이면 손해 없음, 차감 후 답변 중이면 한도 1회가 소모된다.
- **답변 함수의 그 밖의 예외(버그):** 500이며 한도를 되돌리지 않는다. 되돌리면 버그를 반복 호출로 우회할 수 있다.

## 4. 다음 수정

- **M4 (5주차) 화면:** 프론트가 `sessionStorage`에 토큰을 두고 `Authorization: Bearer`로 보낸다. 401이면 로그인 화면으로.
- **배포:** EC2의 `.env`에 `JWT_SECRET`(예: `python -c "import secrets; print(secrets.token_urlsafe(48))"`)을 넣는다. 비면 로그인·질문이 모두 503이다(의도된 동작).
- **프록시 뒤 배포(Caddy):** 시도 제한의 IP는 `request.client.host`다. 프록시 뒤에서는 모두 프록시 IP로 보이므로 uvicorn을 `--proxy-headers --forwarded-allow-ips`로 띄워 실제 접속 IP를 받는다. 그러지 않으면 제한이 아이디 단위로만 동작한다.
- **시도 제한 저장소:** 프로세스 메모리. 서버를 여러 대로 늘리거나 재시작하면 기록이 사라진다 — 늘릴 때 DB·Redis로 옮긴다.
- **로그:** 요청 로그(JSON 한 줄)는 로깅 모듈을 만들 때 추가한다(AGENTS.md "로그").

## 5. 업데이트 시 주의점

- **라우트를 바꾸면** `make generate`로 `docs/generated/openapi.json`을 갱신해 같은 커밋에 넣는다(게이트 1 스냅샷 테스트).
- **`ask`의 순서(검증 → 차감 → 커밋 → 답변 → 503 되돌림)를 바꾸지 않는다.** 차감 커밋을 답변 뒤로 미루면 답변이 도는 동안 같은 학생의 동시 요청이 한도를 넘는다.
- **새 공급사 오류 타입**(예: 다른 임베딩 공급사)을 쓰면 `get_answer_fn`의 `except`와 `is_provider_outage`에 추가해야 503·되돌림이 동작한다.
- **`backend/app/api/`, `backend/app/core/security.py`는 위험 경로**다 — 바꾸면 게이트 3(교차 모델 리뷰).
- **토큰 payload에 필드를 추가하지 않는다.** 필요한 정보는 `current_user`에서 DB로 읽는다.

## 파일 위치

| 파일 | 역할 |
|---|---|
| `backend/app/api/routes.py` | `/api/auth/login`, `/api/me`(화면 상단 수강 과목), `/api/ask`, 요청·응답 모델 |
| `backend/app/api/deps.py` | 세션, `current_user`, `get_answer_fn`(공급사 장애 → `UpstreamError`), `get_login_throttle` |
| `backend/app/api/throttle.py` | 로그인 시도 제한(메모리) |
| `backend/app/core/security.py` | argon2 비밀번호, HS256 토큰 |
| `backend/app/core/users.py` | `make users` 계정 CLI |
| `backend/app/db/accounts.py`, `usage.py` | 계정·수강 저장소, 원자 한도 |
