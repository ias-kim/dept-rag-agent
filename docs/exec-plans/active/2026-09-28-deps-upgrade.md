# 의존성 업그레이드 (보안 + 메이저 버전 선반영)

- 담당: 김성관 · 시작: 2026-09-28 · 관련 주차: 2주차

## 목표
PR #1 게이트 3에서 차단된 starlette 취약 버전(0.41.3)을 벗어나고, 코드가 아직 없는 지금 mcp·anthropic·openai 메이저 버전을 올려 둔다.

## 완료 기준
- [ ] starlette ≥ 0.47.2 (CVE-2025-54121 기준선) — `tests/test_dependency_floor.py`가 강제
- [ ] 주요 라이브러리(fastapi, mcp, anthropic, openai, sqlalchemy, psycopg, pgvector) import 스모크 테스트 통과
- [ ] 모든 버전 `==` 고정, Python 3.12에서 `make setup` → `make check` 통과
- [ ] CI `check` 통과
- [ ] 게이트 3(Codex) 재실행, 차단 없음

## 범위 밖
- 새 버전 API를 쓰는 기능 구현 (3주차 MCP 도구 구현에서)

## 결정 로그
- 2026-09-28: 최신 버전 일괄 고정. 사용 코드가 없어 메이저 변경 비용이 가장 낮은 시점.
