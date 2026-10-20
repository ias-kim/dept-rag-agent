# M4a 화면 2종·정적 서빙·컨테이너 이미지 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- 담당: 김성관 · 시작: 2026-10-20 · 관련 주차: 5주차 (계획서 문장: "프론트엔드 화면 구현 및 백엔드 연동, 근거 출처(파일명·페이지) 표시 완성")

**Goal:** 학생이 브라우저에서 로그인하고 질문하면 답변과 출처(파일명·쪽)·안내를 보여 주는 화면 2종을 만들고, FastAPI가 빌드된 화면을 같은 출처(`/`)에서 서빙하며, 앱+DB를 Docker로 로컬에서 띄워 `make smoke`가 통과하게 한다.

**Architecture:** React 화면은 라우터 라이브러리 없이 "토큰 있음/없음"으로 로그인 화면과 질문 화면을 바꾼다. HTTP는 `src/api.js` 한 곳만 거치고(토큰 `sessionStorage`, `Authorization: Bearer`), 서버 공지 코드는 `src/notices.js`가 한국어 문구로 바꾼다. 운영은 같은 출처라 CORS를 두지 않는다 — 개발 중에는 Vite 프록시가 `/api`를 `:8000`으로 넘긴다. 백엔드는 `frontend/dist`가 있을 때만 정적 파일과 SPA 폴백을 붙이되, `/api/*`·`/health`를 절대 가리지 않는다. 이미지는 멀티 스테이지(Node 빌드 → Python 런타임) 하나.

**Tech Stack:** React 19 · Vite 8 (Node `^20.19.0 || >=22.12.0`) · Vitest + @testing-library/react + jsdom · FastAPI `StaticFiles`/`FileResponse` · Docker 멀티 스테이지 · 기존 compose(pgvector/pgvector:pg16)

**Spec:** [`docs/design/2026-09-28-system-design.md`](../../design/2026-09-28-system-design.md) — §2 응답 형태 `{answer, sources[{file,page,section}], intent, notices[]}`, §4 프론트 `sessionStorage` + Bearer, §7 컨테이너("프론트 빌드 → 백엔드 이미지, FastAPI가 `/` 정적 + `/api/*`"), §8 M4. API 계약 SoT는 `backend/app/api/routes.py`.

## M4 분할 (2026-10-20 결정)

설계 §8의 M4(화면 2종·Docker·CloudFormation·Caddy·배포)를 둘로 나눈다.

- **M4a (이 문서)** — 화면 2종, 정적 서빙, 이미지, 로컬 compose. 계획서 5주차 문장을 그대로 충족한다.
- **M4b (별도 계획)** — CloudFormation·Caddy·DuckDNS·EC2. **스파이크 S3(공용 계정에서 IAM 역할 생성 가능 여부)가 아직 ⏳**([`done/2026-09-29-m1-data-permission.md`](../done/2026-09-29-m1-data-permission.md) "스파이크 결과")라서, S3 결과가 나온 뒤에 계획을 쓴다. 결과에 따라 스택 템플릿 설계가 바뀐다. 배포는 원래 7주차 문장이므로 미뤄도 계획서와 어긋나지 않는다.

## Global Constraints

- 계층 `api → core → mcp → db` 그대로. 정적 서빙 코드는 `app/api/frontend.py`(api 계층)에 둔다. `app.core.config`만 어디서나 import 가능.
- **CORS 미들웨어를 추가하지 않는다.** 운영은 같은 출처, 개발은 Vite 프록시.
- 토큰은 `sessionStorage` 키 `"dept-rag-token"` 하나에만 둔다(`localStorage` 금지 — 탭을 닫으면 사라져야 공용 PC에서 안전).
- 화면 문구는 서버 `detail` 문자열을 그대로 보여 준다(429가 "로그인 시도 과다"와 "오늘 한도 소진" 두 뜻이라 클라이언트가 추측하면 틀린다). `detail`이 배열(422)이면 `"입력값을 확인해 주세요"`.
- 질문 최대 길이 `QUESTION_MAX_CHARS = 500`(`routes.py`)을 화면에서도 같은 값으로 막는다. 값의 원천은 서버 — 화면 상수에 출처 주석을 단다.
- 서버 공지 코드 원문(`tool_error:search_major` 같은 문자열)은 화면에 절대 노출하지 않는다. 모르는 코드는 숨긴다.
- 정적 서빙은 `include_in_schema=False` — `docs/generated/openapi.json` 스냅샷이 바뀌면 안 된다. 바뀌었다면 실수다.
- 이미지에 `.env`·`data/`·`eval/runs/`·`eval/grading/`·`node_modules/`·`docker/volumes/`가 들어가면 안 된다. 비밀값은 실행 시 `env_file`로만.
- uvicorn은 **워커 1개**(로그인 시도 제한 상태가 프로세스 메모리에 있다). `--proxy-headers`는 켜 두고 `FORWARDED_ALLOW_IPS` 환경변수로 신뢰 프록시를 정한다(기본 `127.0.0.1`, M4b에서 Caddy 네트워크로).
- 프론트 의존성은 `npm install -D`로 추가하고 `package-lock.json`을 커밋한다(기존 `^` 표기 관례 유지). Vitest는 `vite@8`을 peer로 허용하는 버전을 고른다 — 설치 시 peer 경고가 나면 버전을 바꾼다.
- 테스트는 실제 API를 부르지 않는다. 프론트는 `fetch`를 `vi.fn()`으로 바꾸고, 백엔드는 임시 dist 폴더로 정적 서빙만 시험한다.
- 커밋: 한국어 conventional + `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. 각 태스크 끝에 `make check` 통과. 브랜치 `feat/m4a-frontend`.
- 각 태스크는 바뀐 동작을 `docs/dev-notes/frontend.md`에 같은 커밋으로 반영한다(AGENTS.md 규칙: 개념 → 흐름 → 실패 모드 → 다음 수정 → 주의점).
- **게이트 3 필수** — `backend/app/api/`, `docker/`가 바뀐다.

## Review Focus

1. **12시간이 지나 토큰이 만료된 채 질문** — `/api/ask`가 401이면 토큰을 지우고 로그인 화면으로 돌아가 "로그인이 만료되었습니다"를 보여야 한다. 질문 화면에 갇혀 같은 오류만 반복되면 안 된다 → Task 4 `expired token returns to login`.
2. **응답을 기다리는 동안 버튼을 또 누름** — 누를 때마다 일일 한도가 깎인다. 요청 중에는 제출 버튼이 비활성이어야 한다 → Task 4 `disables submit while waiting`.
3. **SPA 폴백이 API 오타를 삼킴** — `/api/asks` 같은 없는 API에 `index.html`(200)이 돌아오면 화면은 JSON 파싱 오류로 깨진다. JSON 404여야 한다 → Task 5 `test_unknown_api_path_is_json_404`.
4. **출처 없는 정상 응답(범위 밖·수강생 전용·자료 없음)과 `section: null`** — 빈 출처 목록 제목만 덩그러니 남거나 화면에 `null`이 찍히면 안 된다 → Task 4 `renders answer without sources`, `omits null section`.
5. **`.env`가 이미지에 구워짐** — 이미지를 어디에 올리든 API 키가 샌다 → Task 6 `test_dockerignore_excludes_secrets_and_data`.

M4b로 넘기는 위험(이 계획에서는 기록만): Caddy 뒤에서는 `request.client.host`가 모두 프록시 IP가 되어 IP별 로그인 제한(20회)이 반 전체에 걸린다 → M4b에서 `FORWARDED_ALLOW_IPS`를 Caddy 네트워크로 좁히고 `X-Forwarded-For` 기준 제한을 테스트한다.

---

## 파일 구조

| 파일 | 책임 |
|---|---|
| `frontend/src/notices.js` | 서버 공지 코드 → 화면 문구 (`noticeLabels`) |
| `frontend/src/api.js` | 토큰 보관, `login`·`ask`, 오류를 `ApiError`로 변환 |
| `frontend/src/LoginPage.jsx` | 로그인 폼 |
| `frontend/src/AskPage.jsx` | 질문 입력, 답변·출처·안내 표시, 로그아웃 |
| `frontend/src/App.jsx` | 토큰 유무로 두 화면 전환, 만료 안내 전달 |
| `frontend/src/App.css`, `index.css` | 최소 스타일 (기존 템플릿 스타일 교체) |
| `frontend/src/test/setup.js` | jest-dom 매처, 테스트마다 `sessionStorage` 비우기 |
| `frontend/vite.config.js` | Vitest 설정, `/api`·`/health` 개발 프록시 |
| `backend/app/api/frontend.py` | `add_frontend(app, dist_dir)` — 정적 파일 + SPA 폴백 |
| `backend/app/main.py` | dist가 있으면 `add_frontend` 호출 |
| `docker/Dockerfile`, `.dockerignore` | 멀티 스테이지 이미지, 빌드 제외 목록 |
| `docker/docker-compose.yml` | `app` 서비스(프로필 `app`) 추가 |
| `Makefile` | `test-fe`, `build-fe`, `app-up`, `smoke URL=` |

지울 것: `frontend/src/assets/{hero.png,react.svg,vite.svg}` (템플릿 잔재).

---

### Task 1: 프론트 테스트 하네스 + 공지 문구 매핑 (+ M3b 계획 정리)

**Files:**
- Modify: `frontend/package.json`, `frontend/package-lock.json`, `frontend/vite.config.js`, `Makefile`
- Create: `frontend/src/test/setup.js`, `frontend/src/notices.js`, `frontend/src/notices.test.js`
- Move: `docs/exec-plans/active/2026-09-30-m3b-auth-api.md` → `docs/exec-plans/done/` (PR #14로 병합 완료, 결정 로그 한 줄: "2026-10-20: PR #14 병합으로 완료, 측정은 4주차 비교표")

**Interfaces:**
- Produces: `noticeLabels(codes: string[]): string[]` — 중복 제거된 표시 문구, 숨길 코드는 빠짐. `npm run test`(= `vitest run`), `make test-fe`, `make test`가 `test-py`+`test-fe`를 모두 돌림.

- [ ] **Step 1: 하네스 설치** — `cd frontend && npm install -D vitest @testing-library/react @testing-library/user-event @testing-library/jest-dom jsdom`. `package.json` scripts에 `"test": "vitest run"`. `vite.config.js`에 `test: { environment: 'jsdom', setupFiles: './src/test/setup.js' }`. `setup.js`: `import '@testing-library/jest-dom/vitest'`, `afterEach(() => { cleanup(); sessionStorage.clear(); vi.restoreAllMocks() })`.
- [ ] **Step 2: Makefile** — 기존 `test` 타깃을 `test-py`로 이름 바꾸고 `test-fe: cd frontend && npm run --silent test`, `test: test-py test-fe`. `.PHONY`에 추가. CI는 `make check`만 부르므로 `.github/`는 건드리지 않는다.
- [ ] **Step 3: 실패하는 테스트** — `frontend/src/notices.test.js`

```js
import { noticeLabels } from './notices'

test('maps enrollment notice', () => {
  expect(noticeLabels(['major_requires_enrollment'])).toEqual(['전공 강의자료는 수강생만 볼 수 있어 답변에서 제외했습니다.'])
})
test('collapses tool errors and citation problems into one line each', () => {
  expect(noticeLabels(['tool_error:search_major', 'tool_error:search_academic', 'invalid_citation', 'no_citation']))
    .toEqual(['일부 자료를 검색하지 못했습니다. 답변이 불완전할 수 있습니다.', '출처를 확인하지 못한 문장이 있을 수 있습니다.'])
})
test('truncated', () => {
  expect(noticeLabels(['truncated'])).toEqual(['답변이 길어 중간에 끊겼습니다.'])
})
test('hides codes the answer text already explains, and unknown codes', () => {
  expect(noticeLabels(['out_of_scope', 'no_evidence', 'refused', 'empty', 'something_new'])).toEqual([])
})
```

- [ ] **Step 4: RED 확인** — `make test-fe` → `Failed to resolve import "./notices"`.
- [ ] **Step 5: 구현** — `frontend/src/notices.js`의 `noticeLabels`. `tool_error:` 접두사 매칭, 결과 순서는 처음 나온 순서, 같은 문구 한 번만. 파일 머리 주석: "코드 원천은 `backend/app/core/router.py`·`answer.py`·`pipeline.py`. 서버에 코드가 늘면 여기도 추가 — 빠뜨리면 숨겨질 뿐 깨지지는 않는다."
- [ ] **Step 6: GREEN 확인** — `make check` 통과 (pytest + vitest + 린트).
- [ ] **Step 7: 커밋** — `test(frontend): Vitest 하네스와 공지 코드 문구 매핑` (M3b 계획 이동 포함)

---

### Task 2: API 클라이언트

**Files:**
- Create: `frontend/src/api.js`, `frontend/src/api.test.js`

**Interfaces:**
- Consumes: 서버 계약(`routes.py`) — `POST /api/auth/login {username,password} → {access_token, token_type}`, `POST /api/ask {question} → {answer, sources[{file,page,section}], intent, notices[]}`, 오류 `{detail: string | object[]}`.
- Produces:
  - `TOKEN_KEY = 'dept-rag-token'`, `getToken(): string|null`, `clearToken(): void`
  - `class ApiError extends Error { status: number }` — `message`가 화면에 그대로 나갈 문구
  - `login(username, password): Promise<void>` — 성공 시 토큰 저장
  - `ask(question): Promise<AskResponse>` — 토큰을 Bearer로 붙임
  - `NETWORK_ERROR = '서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.'`

- [ ] **Step 1: 실패하는 테스트** — `fetch`를 `vi.spyOn(globalThis, 'fetch')`로 바꾼다. 응답 헬퍼 `json(status, body)`.

```js
test('login stores token', async () => { /* 200 {access_token:'t1'} → getToken() === 't1', 요청 본문 {username,password}, method POST, url '/api/auth/login' */ })
test('ask sends bearer token and returns body', async () => { /* sessionStorage에 't1' → headers.Authorization === 'Bearer t1', 결과 객체 그대로 */ })
test('string detail becomes message', async () => { /* 429 {detail:'오늘 질문 한도를 모두 사용했습니다'} → rejects ApiError{status:429, message: 같은 문구} */ })
test('422 list detail becomes generic message', async () => { /* 422 {detail:[{...}]} → message '입력값을 확인해 주세요' */ })
test('non-json error body falls back by status', async () => { /* 502 본문 'Bad Gateway'(text) → message NETWORK_ERROR, status 502 */ })
test('network failure', async () => { /* fetch reject(TypeError) → ApiError{status:0, message: NETWORK_ERROR} */ })
test('ask 401 clears token', async () => { /* 401 → getToken() === null, ApiError.status === 401 */ })
```

- [ ] **Step 2: RED 확인** — `make test-fe`.
- [ ] **Step 3: 구현** — 내부 `request(path, body, {auth})` 하나로 두 함수를 만든다. 응답 본문은 `await res.text()` 후 `JSON.parse` 시도(실패 시 null) — 프록시 오류 페이지(HTML)에서 터지지 않게. `detail`이 문자열이 아니고 배열이면 422 문구, 그 외 실패는 `NETWORK_ERROR`. 401이면 `clearToken()` 후 던진다.
- [ ] **Step 4: GREEN 확인** — `make check`.
- [ ] **Step 5: 커밋** — `feat(frontend): API 클라이언트 — 토큰 보관·오류 문구 변환`

---

### Task 3: 로그인 화면과 화면 전환

**Files:**
- Create: `frontend/src/LoginPage.jsx`, `frontend/src/LoginPage.test.jsx`
- Modify: `frontend/src/App.jsx` (템플릿 내용 전부 교체), `frontend/src/App.css`, `frontend/src/index.css`
- Delete: `frontend/src/assets/` 템플릿 이미지 3개
- Create: `frontend/src/App.test.jsx`

**Interfaces:**
- Consumes: Task 2 `login`, `getToken`, `ApiError`
- Produces:
  - `<LoginPage onLoggedIn={() => void} notice={string|undefined} />` — `notice`는 만료 안내 등 위에 띄울 문구
  - `<App />` — `getToken()`이 있으면 `<AskPage onLogout={(reason?: string) => void} />`, 없으면 `<LoginPage>`. `onLogout('expired')`이면 로그인 화면에 `'로그인이 만료되었습니다. 다시 로그인해 주세요.'`
  - Task 4의 `AskPage`가 아직 없으므로 이 태스크에서는 `AskPage.jsx`에 `export default function AskPage() { return <main><h1>질문하기</h1></main> }` 자리표시를 둔다(Task 4에서 교체).

- [ ] **Step 1: 실패하는 테스트** — `LoginPage.test.jsx` (`vi.mock('./api')`)

```jsx
test('submits credentials and calls onLoggedIn', /* 아이디·비밀번호 입력(label '아이디','비밀번호') → '로그인' 클릭 → login('kim','pw') 호출, onLoggedIn 1회 */)
test('shows server message on failure', /* login reject ApiError(401,'아이디 또는 비밀번호가 올바르지 않습니다') → role='alert'에 같은 문구, onLoggedIn 미호출 */)
test('button disabled while pending and when fields empty', /* 빈 칸 → disabled; 대기 중 → disabled */)
test('shows notice prop', /* notice='로그인이 만료되었습니다…' → 화면에 보임 */)
```

`App.test.jsx`:

```jsx
test('shows login when no token', /* heading '로그인' */)
test('shows ask page when token exists', /* sessionStorage에 토큰 → heading '질문하기' */)
```

- [ ] **Step 2: RED 확인** — `make test-fe`.
- [ ] **Step 3: 구현** — 비밀번호 칸은 `type="password"`, `autoComplete="current-password"`. 제출은 `<form onSubmit>`(Enter로도 제출). 화면 머리에 서비스 이름 "학과 지식 질의응답"과 한 줄 안내("계정은 튜터에게 받습니다 — 회원가입 없음").
- [ ] **Step 4: GREEN 확인** — `make check`.
- [ ] **Step 5: 커밋** — `feat(frontend): 로그인 화면과 토큰 기반 화면 전환`

---

### Task 4: 질문·답변 화면 — 출처·안내 표시

**Files:**
- Modify: `frontend/src/AskPage.jsx` (자리표시 교체), `frontend/src/App.css`
- Create: `frontend/src/AskPage.test.jsx`

**Interfaces:**
- Consumes: Task 2 `ask`, `ApiError`, `clearToken`; Task 1 `noticeLabels`; Task 3 `onLogout(reason?)`
- Produces: `QUESTION_MAX_CHARS = 500` export (화면 상수, 원천 `routes.py`)

**표시 규칙 (spec이 정하지 않아 여기서 정한다)**
- 답변 본문의 `[1]`, `[2]`는 서버가 `sources` 순서대로 매긴 번호다(`answer.py` `verify_citations`). 출처 목록을 `<ol>`로 그려 번호가 그대로 맞게 한다. 본문 번호는 텍스트 그대로 둔다(링크화는 범위 밖).
- 출처 한 줄: `파일명 · p.쪽 · 절` — 파일명은 `file`의 마지막 `/` 뒤, `title` 속성에 전체 경로. `section`이 null이면 그 부분을 뺀다.
- `sources`가 비면 "출처" 제목째 그리지 않는다.
- 안내(`noticeLabels(notices)`)는 답변 위 `role="status"` 목록.
- 질문 중에는 버튼 비활성 + "답변을 만드는 중…" 표시. 답변이 오면 질문 칸은 유지(고쳐 묻기 쉽게).

- [ ] **Step 1: 실패하는 테스트** (`vi.mock('./api')`)

```jsx
const full = { answer: '중간고사는 10월 21일입니다 [1].', intent: 'academic',
  sources: [{ file: 'academic/2026-학사일정.pdf', page: 3, section: '2학기' }], notices: [] }

test('shows answer and numbered source', /* 입력 → '질문하기' 클릭 → 답변 문구, listitem '2026-학사일정.pdf · p.3 · 2학기', title 속성 'academic/2026-학사일정.pdf' */)
test('omits null section', /* section:null → 'x.pdf · p.1' 정확히, 'null' 문자열 없음 */)
test('renders answer without sources', /* sources:[], notices:['out_of_scope'] → 답변 보임, '출처' heading 없음, status 영역 없음 */)
test('shows mapped notices only', /* notices:['major_requires_enrollment','tool_error:search_major'] → 문구 2개, 'tool_error' 문자열 없음 */)
test('disables submit while waiting', /* ask를 끝나지 않는 Promise로 → 클릭 후 버튼 disabled, ask 1회만 호출(두 번 클릭해도) */)
test('blank or too long question cannot be sent', /* '   ' → disabled; textarea maxLength === 500 */)
test('expired token returns to login', /* ask reject ApiError(401,…) → onLogout('expired') 호출 */)
test('quota error shows server message', /* ask reject ApiError(429,'오늘 질문 한도를 모두 사용했습니다') → role='alert'에 같은 문구 */)
test('logout clears token', /* '로그아웃' 클릭 → clearToken 호출, onLogout() 호출(인자 없음) */)
```

- [ ] **Step 2: RED 확인** — `make test-fe`.
- [ ] **Step 3: 구현** — 상태: `question`, `pending`, `result|null`, `error|null`. 제출 시 `pending`이면 즉시 return(더블 클릭 방어를 버튼 비활성에만 맡기지 않는다). `intent`는 화면에 쓰지 않는다(디버그 정보, null일 수 있음).
- [ ] **Step 4: GREEN 확인** — `make check`.
- [ ] **Step 5: 개발 서버로 눈으로 확인** — `vite.config.js`에 `server.proxy: { '/api': 'http://localhost:8000', '/health': 'http://localhost:8000' }` 추가 후 백엔드(`uvicorn`)와 `npm run dev`를 띄워 실제 계정으로 질문 1개. (튜터가 직접 — 실제 API 비용 발생)
- [ ] **Step 6: 커밋** — `feat(frontend): 질문·답변 화면 — 번호 맞춘 출처 목록과 안내 표시`

---

### Task 5: 백엔드 정적 서빙과 SPA 폴백

**Files:**
- Create: `backend/app/api/frontend.py`, `backend/tests/test_frontend_static.py`
- Modify: `backend/app/main.py`, `backend/app/core/config.py`

**Interfaces:**
- Produces:
  - `Settings.frontend_dist_dir: Path = Path("frontend/dist")` (env `FRONTEND_DIST_DIR`)
  - `add_frontend(app: FastAPI, dist_dir: Path) -> None` — 반드시 모든 라우터 등록 **뒤에** 호출
  - `main.py`: `if settings.frontend_dist_dir.is_dir(): add_frontend(app, settings.frontend_dist_dir)` — 빌드가 없으면 아무것도 붙이지 않아 pytest·개발 서버가 그대로 뜬다

- [ ] **Step 1: 실패하는 테스트** — `tmp_path`에 `index.html`(`<div id="root">`), `assets/app.js`, `favicon.svg`를 만들고, 새 `FastAPI()`에 `app.api.routes.router`와 `/health`를 붙인 뒤 `add_frontend`. `TestClient`로:

```python
def test_root_serves_index(): ...            # GET / → 200, text/html, 'id="root"', Cache-Control에 no-cache
def test_client_route_falls_back_to_index(): ...  # GET /history/3 → 200 index
def test_asset_served(): ...                 # GET /assets/app.js → 200, javascript 본문
def test_root_file_served(): ...             # GET /favicon.svg → 200 svg
def test_unknown_api_path_is_json_404(): ... # GET /api/asks → 404, application/json
def test_api_and_health_not_shadowed(): ...  # POST /api/ask 토큰 없음 → 401 JSON(또는 키 미설정 503 JSON — dependency_overrides로 Settings 고정해 401로), GET /health → {"status":"ok"}
def test_path_traversal_does_not_escape_dist(): ...  # GET /..%2f..%2fsecret.txt (dist 밖에 secret.txt 생성) → 본문에 secret 내용 없음
def test_openapi_has_no_frontend_routes(): ...  # app.openapi()["paths"]에 "/{path}" 류 없음
```

- [ ] **Step 2: RED 확인** — `make test-py` → `ModuleNotFoundError: app.api.frontend`.
- [ ] **Step 3: 구현** — `/assets`는 `StaticFiles(directory=dist/"assets")` 마운트. 나머지는 `@app.get("/{path:path}", include_in_schema=False)` 하나: `api/`로 시작하면 `JSONResponse({"detail":"Not Found"}, 404)`; `(dist / path).resolve()`가 `dist.resolve()` 안의 파일이면 `FileResponse`; 그 외 `index.html`을 `Cache-Control: no-cache`로. 주석: "폴백이 api를 삼키면 화면은 JSON 대신 HTML을 받아 원인 모를 파싱 오류로 깨진다".
- [ ] **Step 4: GREEN 확인** — `make check`. OpenAPI 스냅샷 테스트가 그대로 통과해야 한다(`make generate` 불필요 — 바뀌면 `include_in_schema` 누락).
- [ ] **Step 5: 커밋** — `feat(api): 빌드된 화면 정적 서빙 — api·health는 가리지 않는 SPA 폴백`

---

### Task 6: 컨테이너 이미지와 로컬 compose

**Files:**
- Create: `docker/Dockerfile`, `.dockerignore`, `backend/tests/structural/test_dockerignore.py`
- Modify: `docker/docker-compose.yml`, `Makefile`

**Interfaces:**
- Consumes: Task 5 `FRONTEND_DIST_DIR`
- Produces: `make build-fe`, `make app-up`(= `docker compose -f docker/docker-compose.yml --profile app up -d --build --wait`), `make smoke URL=…`(기본 `http://localhost:8000`), 앱 컨테이너 포트 `8080:8000`

- [ ] **Step 1: 실패하는 테스트** — `test_dockerignore.py`

```python
REQUIRED = [".env", "data", "eval/runs", "eval/grading", "**/node_modules", "docker/volumes", "**/.venv"]
def test_dockerignore_excludes_secrets_and_data():
    lines = {l.strip() for l in (ROOT / ".dockerignore").read_text().splitlines()}
    assert all(p in lines for p in REQUIRED)
def test_env_example_is_not_required_in_image(): ...  # Dockerfile에 'COPY .env' 문자열 없음
```

- [ ] **Step 2: RED 확인** — `make test-py`.
- [ ] **Step 3: 구현**
  - `.dockerignore`: 위 목록 + `.git`, `frontend/dist`(이미지 안에서 새로 빌드), `**/__pycache__`.
  - `docker/Dockerfile` (빌드 컨텍스트 = 저장소 루트):
    - 1단계 `node:22-alpine` — `frontend/package*.json` 복사 → `npm ci` → 나머지 복사 → `npm run build`
    - 2단계 `python:3.12-slim` — `backend/requirements.txt`만 설치(dev 제외), `backend/` 복사, 1단계 `frontend/dist` → `/app/frontend/dist`, `WORKDIR /app/backend`, `ENV FRONTEND_DIST_DIR=/app/frontend/dist`, 비루트 사용자, `EXPOSE 8000`
    - `CMD ["sh","-c","alembic -c alembic.ini upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers"]` — 주석: 워커 1개인 이유(로그인 제한 상태가 메모리), `FORWARDED_ALLOW_IPS`는 M4b에서 설정
  - compose `app` 서비스: `profiles: ["app"]`, `build: {context: .., dockerfile: docker/Dockerfile}`, `env_file: ../.env`, `environment: DATABASE_URL: postgresql+psycopg://dept_rag:dept_rag@db:5432/dept_rag`(컨테이너 안에서 `localhost:5433`은 틀린 주소), `depends_on: db: condition: service_healthy`, `ports: ["8080:8000"]`, `healthcheck`는 `python -c "urllib.request.urlopen('http://localhost:8000/health')"`.
  - `make db-up`은 프로필이 없어 기존처럼 DB만 띄운다 — 바뀌면 안 된다.
- [ ] **Step 4: GREEN 확인** — `make check`.
- [ ] **Step 5: 이미지 확인 (튜터 로컬)**
  - `make app-up` → 성공, `make smoke URL=http://localhost:8080` → `{"status":"ok"}`
  - `curl -s localhost:8080/ | grep 'id="root"'` → 한 줄
  - `curl -s -o /dev/null -w '%{http_code}' -X POST localhost:8080/api/ask` → `401`
  - `docker compose -f docker/docker-compose.yml run --rm app sh -c 'ls -a /app; test ! -e /app/.env && test ! -e /app/backend/.env && echo no-env'` → `no-env`
  - 이 DB 볼륨은 개발 DB와 같다(`docker/volumes/db`) → 적재된 자료·계정 그대로 브라우저 `localhost:8080`에서 로그인·질문 1회
- [ ] **Step 6: 커밋** — `feat(docker): 화면 포함 멀티 스테이지 이미지와 로컬 compose app 프로필`

---

### Task 7: 문서·마무리

**Files:**
- Create/finish: `docs/dev-notes/frontend.md` (Task 1~6에서 쌓은 내용 정리)
- Modify: `AGENTS.md`(명령 표: `make test-fe`·`build-fe`·`app-up`·`smoke URL=`, 개발 서버 `cd frontend && npm run dev`), `docs/sot.md`(행 추가: "화면 공지 문구 | `frontend/src/notices.js` | 화면 | `notices.test.js`", "컨테이너 이미지 | `docker/Dockerfile`·`.dockerignore` | compose | `test_dockerignore.py`"), 설계 §8 표(M4 → M4a·M4b 분할, 결정 날짜), `README.md` 실행 방법에 화면 실행 한 단락
- Move: 이 계획 → `done/`, 결정 로그 기록

- [ ] **Step 1: dev-note 점검** — 불변 조건마다 `조건 → 깨지면 → 지키는 장치`. 최소: ①폴백이 api를 가리지 않음 ②토큰은 sessionStorage에만 ③서버 detail 문구 그대로 ④출처 번호 = sources 순서 ⑤이미지에 .env 없음 ⑥워커 1개.
- [ ] **Step 2: `make check` 통과**
- [ ] **Step 3: 화면 캡처 2장 (튜터)** — 로그인 화면, 출처가 붙은 답변 화면. 5주차 보고서 첨부용(`보고서/5주차/`).
- [ ] **Step 4: 게이트 2(reviewer) → 게이트 3(Codex, `backend/app/api/`·`docker/` 변경)** 결과를 PR 코멘트로.
- [ ] **Step 5: 커밋·PR** — `docs: M4a dev-note(frontend)·명령·SoT·설계 §8 분할`

## 완료 기준 (reviewer가 이걸로 판정한다)

- [ ] `make check`가 pytest와 vitest를 모두 돌리고 통과
- [ ] 로그인 실패·한도 초과·만료 토큰·네트워크 오류에서 화면이 서버 문구 또는 정해진 문구를 보여 준다 (Task 2·3·4 테스트)
- [ ] 출처 목록 번호가 답변 본문 `[n]`과 맞고, 출처 없는 응답·`section: null`이 깨지지 않는다 (Task 4)
- [ ] `/api/*` 오타는 JSON 404, `/health`·`/api/ask`는 정적 서빙 뒤에도 그대로, OpenAPI 스냅샷 불변 (Task 5)
- [ ] `make app-up` 후 `make smoke URL=http://localhost:8080` 통과, 이미지에 `.env` 없음 (Task 6)
- [ ] `docs/dev-notes/frontend.md`, AGENTS·SoT·설계 §8 갱신

## 범위 밖

- AWS(CloudFormation·EC2·Caddy·DuckDNS·HTTPS) → **M4b**, 스파이크 S3 결과 이후
- 본문 `[n]`을 클릭 가능한 링크로 바꾸기, 대화 기록·멀티턴(설계 결정 10), 남은 한도 표시(API 없음)
- 회원가입·비밀번호 변경(계정은 `make users`만)

## 결정 로그

- 2026-10-20: M4를 M4a(화면·이미지)·M4b(AWS 배포)로 분할 — 스파이크 S3 미확인 상태에서 스택 템플릿을 쓰면 다시 써야 할 수 있음. 5주차 계획서 문장은 M4a로 충족.
- 2026-10-20: 라우터 라이브러리 없이 토큰 유무로 화면 전환 — 화면 2개뿐.
- 2026-10-20: 공지 코드는 화면에서 문구로 바꾸고 모르는 코드는 숨김 — 코드 원문이 학생에게 보이면 안 되고, 서버에 코드가 늘어도 화면이 깨지지 않게.
