# 화면(프론트엔드) — 5주차 로그인·질문 화면

> 마지막 갱신: 2026-10-20 · 계획: [`docs/exec-plans/done/2026-10-20-m4a-frontend.md`](../exec-plans/done/2026-10-20-m4a-frontend.md) · 설계 §2·§4·§7

## 1. 핵심 개념

**서버 공지 코드는 화면 문구로 바꿔서 보인다.** 서버는 `notices`에 기계용 코드(`major_requires_enrollment`, `tool_error:search_major` …)를 담는다. 학생에게 코드 원문을 보이면 안 되므로 `src/notices.js`의 `noticeLabels`가 문구로 바꾸고, 모르는 코드와 답변 본문이 이미 설명하는 코드(`out_of_scope`·`no_evidence`·`refused`·`empty`)는 숨긴다.

## 2. 데이터 흐름

```
(2026-10-20 B안 리디자인: 검색형 — 큰 제목·설명·검색창·예시 질문, 답변 카드, "이 답변의 근거 자료" 목록, 상단 수강 과목 배지)

LoginPage ─ login(username, password) ─▶ POST /api/auth/login ─▶ sessionStorage[dept-rag-token]
   │ onLoggedIn
App (토큰 있음?) ──▶ AskPage
   │ me() ─▶ GET /api/me ─▶ {username, courses} → 상단 배지 ("AGENT · DB 수강" / "게스트 · 학사 자료만")
   │   └ 401이면 바로 onLogout('expired') — 만료된 토큰으로 질문을 다 쓴 뒤에야 튕기지 않게. 그 외 실패는 배지만 숨김
   │ ask(question) ─▶ POST /api/ask (Bearer) ─▶ {answer, sources[{file,page,section}], intent, notices[]}
   │   ├─ answer      → 본문의 반각 [n]을 번호 배지(aria-label "출처 n")로 — 서버가 자료 원문의 [1]은 전각으로 바꿔 두므로 반각은 검증된 인용뿐
   │   ├─ sources     → <ol> 출처 목록 (번호 = 본문 [n]), 비면 "출처" 제목째 생략
   │   ├─ notices     → noticeLabels → 안내 띠(role=status), 비면 생략. 수강 안내는 출처가 있을 때만(없으면 본문과 같은 말)
   │   └─ intent      → 화면에 쓰지 않음 (baseline 모드에서는 null)
   └ 401 → onLogout('expired') → LoginPage에 만료 안내
```

**운영(같은 출처):** `npm run build` → `frontend/dist`. `app/main.py`가 dist가 있으면 `add_frontend`로 `/assets/*`(정적)와 `/{path}`(SPA 폴백)를 **모든 라우트 뒤에** 붙인다. `/api/*`·`/health`가 먼저 매칭되고, 폴백은 `api/`로 시작하면 JSON 404, dist 안의 실제 파일이면 그 파일, 나머지는 `index.html`(`Cache-Control: no-cache`).

**컨테이너:** `make app-up` → `docker/Dockerfile` 멀티 스테이지(Node 22로 `npm ci && npm run build` → `python:3.12-slim`에 `backend/app`·`migrations`·`dist`만 복사). 시작 시 `alembic upgrade head` 후 uvicorn 워커 1개. compose `app` 서비스(프로필 `app`)는 저장소 루트 `.env`를 `env_file`로 받고 `DATABASE_URL`만 `db:5432`로 덮어쓴다. 호스트 포트 8080 → `make smoke URL=http://localhost:8080`.

**개발 실행:** 백엔드 `cd backend && .venv/bin/uvicorn app.main:app --reload`(:8000) + `cd frontend && npm run dev`(:5173). Vite 프록시가 `/api`·`/health`를 :8000으로 넘긴다.

## 3. 불변 조건과 실패 모드

| 조건 | 깨지면 생기는 문제 | 지키는 장치 |
|---|---|---|
| 토큰은 `sessionStorage`(`dept-rag-token`)에만 둔다 | `localStorage`로 바꾸면 공용 PC에서 탭을 닫아도 다음 사람이 로그인된 채로 질문한다(한도·권한 도용) | `api.js` `TOKEN_KEY`, `api.test.js` |
| 오류 문구는 서버 `detail` 문자열 그대로 | 429를 화면이 "한도 소진"으로 단정하면 로그인 시도 과다 상황에 틀린 안내가 나간다 | `api.js` `errorMessage`, `api.test.js::string detail becomes message` |
| 401이면 토큰을 지운다 | 12시간 지나 만료된 토큰을 계속 보내며 같은 오류만 반복한다 | `api.js` `request`, `api.test.js::ask 401 clears token` |
| JSON이 아닌 오류 본문(프록시 502 HTML)에서도 깨지지 않는다 | `JSON.parse` 예외로 화면 전체가 멈춘다 | `api.js` 본문 파싱 실패 허용, `api.test.js::non-json error body…` |
| 출처 목록 순서 = 서버 `sources` 순서 | 본문 `[2]`가 다른 파일을 가리켜 학생이 엉뚱한 쪽을 근거로 믿는다 | `AskPage.jsx` `SourceList`(정렬·중복 제거 금지), `answer.py` `verify_citations` |
| 요청 중에는 다시 보내지 않는다 | 연타할 때마다 일일 한도가 깎인다 | `AskPage.jsx` `pending` 조기 반환 + 버튼 비활성, `AskPage.test.jsx::disables submit while waiting` |
| `section: null`·빈 `sources`가 깨지지 않는다 | 화면에 `null` 글자나 빈 "출처" 제목이 보인다 | `AskPage.test.jsx::omits null section`, `renders answer without sources` |
| SPA 폴백은 `/api/*`·`/health`를 가리지 않고, 없는 API는 메서드와 무관하게 JSON 404 | API 오타에 `index.html`(200)이 돌아가 화면이 JSON 파싱 오류로 깨지거나, POST 오타가 405 "Method Not Allowed"(영어)로 학생 화면에 뜬다 | `add_frontend`를 라우트 등록 뒤 호출(`main.py`), `/api`·`/api/{rest}` 전 메서드(HEAD·OPTIONS 포함) catch-all, `test_unknown_api_path_is_json_404`, `…_for_every_method` |
| 폴백은 dist 밖 파일을 내보내지 않는다 | `/../.env` 같은 경로로 서버 비밀값이 새어 나간다 | `frontend.py` `resolve()` + `is_relative_to(dist)`, `test_path_traversal_does_not_escape_dist` |
| 정적 라우트는 OpenAPI에 나오지 않는다 | `docs/generated/openapi.json` 스냅샷이 바뀌어 계약 문서에 화면 경로가 섞인다 | `include_in_schema=False`, `test_openapi_has_no_frontend_routes` |
| `frontend_dist_dir` 기본값은 실행 위치와 무관한 절대 경로 | `backend/`에서 띄운 uvicorn이 상대 경로를 못 찾아 화면 없이 API만 뜬다(오류 없음) | `config.py` `REPO_ROOT`, `test_default_dist_dir_is_repo_frontend_regardless_of_cwd` |
| 이미지에 `.env`·`data/`·평가 산출물이 없다 | 이미지를 레지스트리·서버에 올리는 순간 API 키와 강의 원문이 같이 나간다 | `.dockerignore`, Dockerfile에 `COPY .`·`COPY .env` 없음, `structural/test_dockerignore.py` |
| uvicorn 워커는 1개 | 로그인 시도 제한이 프로세스 메모리라 워커 수만큼 제한이 풀린다 | Dockerfile `CMD` `--workers 1` (테스트 없음 — 바꿀 때 `throttle.py`를 DB·Redis로 옮겨야 함) |
| 컨테이너 안 `DATABASE_URL`은 `db:5432` | `.env`의 `localhost:5433`이 그대로 쓰이면 마이그레이션 단계에서 연결 실패로 컨테이너가 재시작을 반복한다 | `docker-compose.yml` `app.environment` |
| 500(처리 안 된 예외)은 "서버 오류", 502~504만 "연결할 수 없음" | 공급사 키 오류 같은 서버 문제를 학생이 자기 인터넷 문제로 오해한다 | `api.js` `errorMessage`, `api.test.js::internal server error…` |
| Enter는 보내기, Shift+Enter는 줄바꿈, 한글 조합 중 Enter는 무시 | 조합 중 Enter로 보내면 마지막 글자가 빠진 질문이 나가고 한도가 깎인다 | `AskPage.jsx` `handleKeyDown`(`isComposing`), `AskPage.test.jsx::Enter sends, Shift+Enter adds a line` |
| `App`의 `onLogout`은 `useCallback`으로 고정 | `AskPage`의 `/api/me` effect가 렌더마다 다시 돈다 | `App.jsx` `handleLogout` |
| 글꼴은 npm `pretendard`로 번들 | CDN이 막힌 망에서 글꼴이 바뀌어 줄 간격·폭이 달라진다 | `index.css` `@import 'pretendard/…'` |
| 공지 코드 원문은 화면에 나가지 않는다 | `tool_error:search_major` 같은 내부 이름이 학생에게 보인다 | `notices.js` 기본값 숨김, `notices.test.js` |

## 4. 다음 수정

- **M4b(배포):** Caddy 뒤에서는 `request.client.host`가 모두 프록시 IP가 되어 IP별 로그인 제한(20회)이 반 전체에 걸린다 → `FORWARDED_ALLOW_IPS`를 Caddy 네트워크로 지정하고 `X-Forwarded-For` 기준 제한을 테스트한다.
- 공급사 인증 오류(잘못된 API 키)는 지금 500이다 — 키를 고칠 때까지 모든 질문이 실패하고 한도도 돌려주지 않는다. 운영 전 `.env` 키 확인을 배포 점검표에 넣는다.
- 본문 `[n]`을 눌러 출처로 이동하는 링크, 남은 한도 표시(API 없음), 대화 기록 — 범위 밖(M4a 계획).

## 5. 업데이트 시 주의점

- `main.py`에 라우트를 추가할 때는 `add_frontend` 호출보다 **위에** 둔다. 아래에 두면 폴백이 먼저 받아 그 라우트는 영영 호출되지 않는다.
- 화면을 고친 뒤 `uvicorn`으로 확인하려면 `npm run build`를 다시 해야 한다(개발 중에는 `npm run dev`가 편하다).
- 서버에 공지 코드를 추가하면 `frontend/src/notices.js`에도 추가한다. 빠뜨리면 그 안내가 조용히 숨겨진다.
- 프론트 테스트는 `make test`(= `test-py` + `test-fe`)에 포함된다. CI도 `make check`로 같이 돈다.

## 파일 위치

| 파일 | 역할 한 줄 |
|---|---|
| `frontend/src/api.js` | 서버와의 유일한 통로 — 토큰 보관, 오류 문구 변환 |
| `frontend/src/notices.js` | 공지 코드 → 학생용 문구 |
| `frontend/src/App.jsx` | 토큰 유무로 로그인/질문 화면 전환 |
| `frontend/src/questions.js` | 질문 최대 길이(서버와 같은 값), 예시 질문 |
| `frontend/src/LoginPage.jsx`, `AskPage.jsx` | 화면 2종 |
| `backend/app/api/frontend.py` | 빌드 결과 정적 서빙 + SPA 폴백 |
| `docker/Dockerfile`, `.dockerignore`, `docker/docker-compose.yml` `app` | 화면+API 이미지와 로컬 실행 |
