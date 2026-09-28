# 하네스 프로필 — 이 프로젝트 하네스 설정의 SoT

작성: 2026-09-28 · 근거: KSG Harness Bootstrap (8원칙 + 4패턴)

## 인터뷰 결과

| 항목 | 값 |
|---|---|
| 프로젝트 성격 | 형식상 팀(5인, 1~3학년) 튜터링 프로젝트 + 포트폴리오. 기간 2026-09-10 ~ 11-07 |
| **실제 개발 인원** | **1인 (튜터 김성관).** 튜티 4명은 코드 대신 TIL·학습 산출물로 기여 |
| 스택 | Python 3.12 · FastAPI · MCP Python SDK · PostgreSQL+pgvector · React+Vite · Docker+AWS EC2 |
| API 형태 | REST (FastAPI → OpenAPI) |
| 코딩 에이전트 | Claude Code + Codex 혼용 → `AGENTS.md`가 공통 지도, `CLAUDE.md`는 import + 전용 메모 |
| CI | GitHub Actions (`.github/workflows/check.yml`) |
| 위험 영역 | 권한 분리(MCP 도구 노출·검색 SQL 필터), DB·메타데이터 스키마, 의존성, 배포·CI, 비밀값 |
| 교차 모델 검증 | Codex CLI 사용 가능 (2026-09-28 기준 로컬 설치 링크 깨짐 — 복구 필요) |
| 목표 레벨 | **Lv.3** (위험 경로 변경 시에만 게이트 3) |

## 게이트

| 게이트 | 내용 | 언제 | 명령/주체 |
|---|---|---|---|
| 1 기계 | ruff + oxlint + pytest(계층 구조·TIL 경로·OpenAPI 스냅샷 포함) | 모든 push/PR | `make check` (CI 동일) |
| 2 의미 | 작성 세션과 분리된 리뷰어가 SoT·ADR·exec-plan 완료 기준과 대조 | 모든 PR | Claude Code `reviewer` 서브에이전트 |
| 3 교차 모델 | 다른 벤더 모델(Codex)이 diff 리뷰 | 위험 경로 변경 PR만 | Codex CLI/플러그인으로 diff 리뷰 → 결과 요약을 PR 코멘트에 첨부 |

위험 경로 목록: [`risk-paths.txt`](risk-paths.txt) (CI가 이 파일을 읽어 경고)

## 1인 개발이라서 달라지는 점

일반 팀 프로젝트는 "다른 사람이 리뷰한다"로 작성자와 검증자를 나눈다. 여기서는 사람 리뷰어가 없다.

- **게이트 2는 모든 PR에 사실상 필수.** 작성자와 검증자를 분리할 수단이 `reviewer` 서브에이전트(별도 컨텍스트)뿐이다. 판정 결과를 PR 코멘트로 남긴다.
- **게이트 3은 유일한 외부 시선.** 위험 경로를 바꿀 때는 다른 벤더 모델이 사람 리뷰어 역할을 대신한다.
- **브랜치 보호는 "CI(`check`) 통과 필수"만.** 자기 PR을 스스로 승인할 수 없으므로 "승인 필수"는 걸지 않는다.
- **튜티 커밋은 `til/`에만.** 튜티 커밋을 지키는 장치는 TIL 경로 구조 테스트다. 튜티가 `backend/`·`frontend/`를 바꾸면 리뷰어가 경고한다.
- 병렬 에이전트 팬아웃, 역할별 전용 리뷰어는 만들지 않는다(1인 규모에 과함).

## 버전 고정 이유

- Python 3.12: 팀 기준 버전. (최초 고정 사유: `psycopg-binary==3.2.3`에 cp314 wheel 없음, 2026-09-28)
- 의존성: 2026-09-28 최신으로 일괄 고정 → [`exec-plans/…/2026-09-28-deps-upgrade.md`](../exec-plans/active/2026-09-28-deps-upgrade.md)
- 보안 하한선: starlette ≥ 0.47.2, `backend/tests/test_dependency_floor.py`가 강제

## 운영

- GC 주기: **월 1회** (매월 첫 주) → [`gc-checklist.md`](gc-checklist.md)
- 관측: JSON 한 줄 로그(AGENTS.md "로그"), 스모크 `make smoke`
