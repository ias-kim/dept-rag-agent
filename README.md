# dept-rag-agent

학과 지식 질의응답 AI 에이전트 — 학생이 질문하면 의도를 분석해 전공자료와 학사·공지자료 중 알맞은 쪽을 검색하고, 근거 출처와 함께 답변하는 서비스.

제27기 백호 튜터링 · ITogether 팀

## 아키텍처

```
학생 질문 → AI Agent(의도 분석/라우터) → MCP 도구 선택
                                              ├─ 전공자료 검색 (수강생 한정)
                                              └─ 학사·공지자료 검색 (전체 공개)
                                                        │
                              근거 출처(파일명·페이지) 표시 → 답변 생성
```

설계 원칙:
1. RAG 파이프라인은 하나, 색인만 전공용/학사용 2종으로 분리
2. 1주차는 워크플로우로 시작 → 6주차에 에이전트로 확장 (의도 분석·답변 생성만 LLM, 나머지는 코드)
3. 권한은 두 겹 — 도구 목록 노출 필터(비용 절감) + 검색 조회 필터(실제 방어선)

## 기술 스택

| 구분 | 선정 |
|---|---|
| 백엔드 | Python, FastAPI |
| AI 기능 연결 | MCP (Python SDK) |
| 답변 생성 | Anthropic Claude API |
| 임베딩 | OpenAI text-embedding-3-small |
| 저장·검색 | PostgreSQL + pgvector |
| 프론트엔드 | React + Vite |
| 배포 | Docker + AWS EC2 |

## 디렉터리 구조

```
backend/        FastAPI 백엔드 + MCP 서버
  app/
    api/        라우터 (질문 엔드포인트 등)
    core/       설정, 라우팅/의도분석 로직
    db/         DB 세션, pgvector 스키마
    mcp/        MCP 도구 정의 (전공자료 검색 / 학사자료 검색)
  tests/        pytest
frontend/       React + Vite 프론트엔드
docker/         docker-compose, Dockerfile
docs/           요구사항 정의서, 구조도 등
til/{이름}/     팀원별 학습 기록 (매주 1편 이상)
```

## 로컬 개발 환경 세팅

```bash
# 백엔드
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# 프론트엔드
cd frontend
npm install
npm run dev

# DB (PostgreSQL + pgvector)
docker compose -f docker/docker-compose.yml up -d
```

## TIL 규칙

`til/{이름}/{날짜}.md` 형식으로 매주 1편 이상 작성 후 커밋.

## 팀

| 학년 | 이름 | 역할 |
|---|---|---|
| 3학년(튜터) | 김성관 | 라우터, MCP 도구 노출, 권한 분리, 배포 |
| 2학년 | 이가을, 서정진 | MCP 서버·클라이언트 구조 학습 → 검색 도구 구현, 배포 연동 |
| 1학년 | 최나원, 홍유정 | Python 기초 → RAG·MCP 개념, 자료 정리 스크립트 |
