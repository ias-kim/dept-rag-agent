# SoT 표 — 사실 유형별 원천

규칙: 사실 하나에 원천 하나. `AGENTS.md`·`README.md`에는 값을 복사하지 않고 경로만 가리킨다.

| 사실 유형 | SoT | 파생 | 일치 점검 방법 |
|---|---|---|---|
| API 계약 | `backend/app/` FastAPI 라우트·Pydantic 모델 | `docs/generated/openapi.json` | `make generate` + `tests/test_openapi_snapshot.py` (게이트 1) |
| 청크 메타데이터 스키마 (`source`·`page`·`section`·`scope`·`course`) | `backend/migrations/versions/0001_initial_schema.py` (`documents.path`, `chunks.page/section/scope/course_code`) | 출처 표시, 검색 필터, 평가셋 | `tests/db/test_schema.py` (게이트 1) |
| DB 구조 | `backend/migrations/` (Alembic) | `backend/app/db/models.py` | `tests/db/test_schema.py` (차원·인덱스) |
| 계층 의존 규칙 | `ARCHITECTURE.md` | `tests/structural/test_layers.py` | 구조 테스트 (게이트 1) |
| 도구 노출·접근 권한 정책 | `ARCHITECTURE.md` "권한 두 겹" (6주차 권한 설계 문서로 이관) | `app/mcp` 노출 필터, `app/db` 조회 필터 | reviewer 서브에이전트 (게이트 2) |
| 환경 설정 키 목록 | `.env.example` | README 설정 설명 | 링크만 |
| Python 의존성 | `backend/requirements.txt`, `requirements-dev.txt` | CI 설치 | CI 설치 성공 |
| 프론트 의존성 | `frontend/package-lock.json` | CI `npm ci` | CI 설치 성공 |
| 위험 경로 목록 | `docs/harness/risk-paths.txt` | CI 경고, profile 설명 | CI가 직접 읽음 |
| TIL 경로 규칙 | `tests/structural/test_til_layout.py` | README "TIL 규칙" | 구조 테스트 (게이트 1) |
| 설계 결정 | `docs/adr/*.md` | AGENTS.md는 링크만 | - |
| 시스템 설계 (흐름·데이터·권한·평가·배포·순서) | `docs/design/2026-09-28-system-design.md` | exec-plan, ADR, ARCHITECTURE.md | reviewer (게이트 2) |
| 평가셋 | `eval/questions.yaml` (+ `eval/FROZEN`) | 평가 실행 기록, 비교표 | `tests/evaluation/test_eval_set.py` (동결 검사, 게이트 1) |
| 채점 기준 | `eval/RUBRIC.md` | `eval/grading/*.csv` | - |
| 답변 생성 프롬프트 | `backend/app/core/prompts/answer.md` | 평가 실행 meta의 `prompt_hash` | 실행 기록 |
| 평가 비교표 | `eval/runs/`, `eval/grading/` (로컬) | `docs/generated/eval-comparison.md` | `make eval-report` 재생성 |
