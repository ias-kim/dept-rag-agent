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

Python 3.12 · FastAPI · MCP · Claude API · pgvector · React+Vite · Docker+EC2

버전과 선정 근거는 [`docs/harness/profile.md`](docs/harness/profile.md), 의존성 원본은 [`docs/sot.md`](docs/sot.md)를 봅니다.

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
docs/           요구사항 정의서, 구조도, 하네스(sot.md, adr/, harness/)
til/{이름}/     팀원별 학습 기록 (매주 1편 이상)
```

## 로컬 개발 환경 세팅

필요: Python 3.12, [uv](https://docs.astral.sh/uv/), Node 20+, Docker

```bash
make setup                                           # backend/.venv(3.12) + frontend 의존성
docker compose -f docker/docker-compose.yml up -d    # DB (PostgreSQL + pgvector)
cd backend && .venv/bin/uvicorn app.main:app --reload
cd frontend && npm run dev
make check                                           # 커밋 전 검증 (CI와 동일)
```

명령 전체와 작업 규칙은 [`AGENTS.md`](AGENTS.md)에 있습니다.

## TIL 규칙

`til/{이름}/{YYYY-MM-DD}.md` 형식으로 매주 1편 이상 작성 후 커밋. 규칙을 어기면 `make check`가 실패합니다.

## 튜티용: 내려받기와 TIL 올리기

코드를 실행할 필요는 없습니다. TIL만 올리면 됩니다. 작성 형식은 [`til/_example.md`](til/_example.md)를 참고하세요.

**방법 1 — GitHub 웹에서 바로 (설치 없음, 1학년 추천)**

1. 저장소의 `til/{내 이름}/` 폴더로 이동
2. **Add file → Create new file** → 파일 이름을 `2026-10-01.md`처럼 날짜로 입력
3. 내용 작성 후 **Commit changes**

**방법 2 — 내 컴퓨터로 내려받아서**

```bash
git clone https://github.com/ias-kim/dept-rag-agent.git   # 처음 한 번
cd dept-rag-agent
git pull                                                  # 작성 전에 항상 최신으로
# til/{내 이름}/YYYY-MM-DD.md 작성
git add til/
git commit -m "docs(til): 홍길동 2026-10-01"
git push
```

`git push`가 거절되면 `git pull` 후 다시 `git push` 하세요. 다른 사람의 TIL이 먼저 올라온 경우입니다.

## 팀

| 학년 | 이름 | 역할 |
|---|---|---|
| 3학년(튜터) | 김성관 | 라우터, MCP 도구 노출, 권한 분리, 배포 |
| 2학년 | 이가을, 서정진 | MCP 서버·클라이언트 구조 학습 → 검색 도구 구현, 배포 연동 |
| 1학년 | 최나원, 홍유정 | Python 기초 → RAG·MCP 개념, 자료 정리 스크립트 |
