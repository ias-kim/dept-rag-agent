# AGENTS.md — dept-rag-agent 지도

학과 지식 질의응답 AI 에이전트. 질문 의도를 분석해 전공자료/학사·공지자료 중 알맞은 색인을 MCP 도구로 검색하고, 근거 출처(파일명·페이지)와 함께 답한다.
이 파일은 **지도**다. 사실(스키마·계약·설정값)은 여기 복사하지 않고 원천을 가리킨다 → [`docs/sot.md`](docs/sot.md)

## 명령

| 목적 | 명령 | 비고 |
|---|---|---|
| 설치 | `make setup` | Python **3.12** 고정(uv 필요), 프론트 `npm ci` |
| 린트 | `make lint` | ruff(backend) + oxlint(frontend) |
| DB 기동 | `make db-up` | `make test`/`make check` 전에 필요 · 로컬 포트 5433 (CI는 서비스 컨테이너) |
| 테스트 | `make test` | pytest, 구조 테스트 포함 · DB 필요 |
| 생성 | `make generate` | 파생물 재생성 → `docs/generated/` |
| **게이트 1 전체** | `make check` | CI와 동일. 끝내기 전에 반드시 통과 |
| 적재 | `make migrate && make ingest` | `data/academic/…`, `data/major/<과목코드>/…` PDF |
| 스모크 | `make smoke` | 서버 실행 중 `/health` 확인 |

서버 실행: `cd backend && .venv/bin/uvicorn app.main:app --reload`

## 계층 규칙 (강제됨)

`api → core → mcp → db` 한 방향만. 역방향 import는 `backend/tests/structural/test_layers.py`가 실패시킨다.
예외: `app.core.config`는 어디서나 import 가능. 상세와 이유 → [`ARCHITECTURE.md`](ARCHITECTURE.md)

## 절대 규칙

1. **권한은 두 겹** — 도구 노출 필터 + 검색 조회(SQL) 필터. 조회 필터 없는 검색 코드는 병합 금지.
2. **MCP 도구는 읽기 전용.** 쓰기·삭제 도구 추가 금지.
3. **`docs/generated/`는 손으로 고치지 않는다.** 소스를 고치고 `make generate`.
4. **`.env`는 읽지 않는다.** 실제 키가 있다. 설정 목록은 `.env.example`.
5. **TIL은 `til/{이름}/{YYYY-MM-DD}.md`.** 구조 테스트가 검사한다.

## 작업 흐름

1. **시작 전** — `docs/exec-plans/active/<YYYY-MM-DD>-<주제>.md`를 만든다. 템플릿: [`docs/exec-plans/README.md`](docs/exec-plans/README.md). 완료 기준을 먼저 적는다.
2. **구현** — 테스트 먼저(RED 확인) → 최소 구현(GREEN) → 정리.
3. **확인** — `make check` 통과. API를 건드렸으면 `make generate` 결과도 커밋.
4. **리뷰** — Claude Code: `reviewer` 서브에이전트(게이트 2). 위험 경로를 건드렸으면 교차 모델 리뷰(게이트 3).
5. **마무리** — 작은 PR로 병합, exec-plan을 `done/`으로 옮기고 결정 로그를 남긴다.

## 문서 지도

| 알고 싶은 것 | 위치 |
|---|---|
| 어떤 사실이 어디에 원본으로 있나 | [`docs/sot.md`](docs/sot.md) |
| 계층·모듈 구조 | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| 설계 결정과 이유 | [`docs/adr/`](docs/adr/) |
| 하네스 설정·게이트·위험 경로 | [`docs/harness/profile.md`](docs/harness/profile.md) |
| 정기 정리 체크리스트 | [`docs/harness/gc-checklist.md`](docs/harness/gc-checklist.md) |
| 진행 중 작업 | [`docs/exec-plans/active/`](docs/exec-plans/active/) |
| 외부 라이브러리 요약 | [`docs/references/`](docs/references/) |
| 팀·스택·실행 소개 | [`README.md`](README.md) |

## 로그

백엔드 로그는 JSON 한 줄 형식(`{"ts","level","event","request_id",...}`)으로 통일한다. 포맷 정의는 로깅 모듈을 만들 때 `backend/app/core/logging.py`에 둔다(아직 없음).
