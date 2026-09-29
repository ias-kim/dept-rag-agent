# 시스템 설계 — 학과 지식 질의응답 에이전트

- 상태: 초안 (검토 대기)
- 작성: 2026-09-28 · 브레인스토밍 세션 결과
- 전제: 제출한 학습계획서(주차별 목표·산출물)는 바꿀 수 없는 제약으로 본다.
- 개발 인원: 1인(튜터). 튜티는 TIL로 기여 → [`docs/harness/profile.md`](../harness/profile.md)

## 0. 목적과 성공 기준

학생이 질문하면 의도를 분석해 전공자료(수강생 한정) 또는 학사·공지자료(전체 공개)를 검색하고, 근거 출처(파일명·페이지)와 함께 답한다.

| 성공 기준 | 측정 |
|---|---|
| HTTPS 배포 URL에서 로그인 후 질문·답변 | `make smoke URL=…` |
| 비수강생은 전공 조각을 어떤 경로로도 받지 못함 | 권한 테스트 행렬 (§4) |
| 출처는 실제 검색된 조각에서만 생성 | 출처 검증 코드 + 출처 일치 지표 |
| 3주차·7주차 동일 평가셋 비교표 | `make eval-report` (§5) |

## 1. 결정 요약

| # | 빈틈 | 결정 |
|---|---|---|
| 1 | 수강생 판별 | 사전 생성 계정 + 수강 과목 DB 매핑 + JWT. **역할·과목은 토큰→DB에서 서버가 꺼내며 LLM 인자로 받지 않는다** |
| 2 | MCP 구조 | 요청마다 `UserContext`를 주입해 MCP 서버를 생성, 같은 프로세스 메모리 전송으로 클라이언트 연결 |
| 3 | 라우터 | 4주차: 분류(LLM) → 처리 표(코드) 워크플로우. 6주차: tool calling 루프. 같은 4종 라벨로 측정 |
| 4 | 근거 부족 | 기준 점수로 조각 제거 → 0건이면 LLM 미호출. 조각 ID 인용 강제, 인용 ID 코드 검증, 출처 문자열은 메타데이터로 코드가 생성 |
| 5 | 평가 채점 | 자동 3종(의도·recall@k·출처) + 답변 정확도는 사람 전수 채점. 제출용 30 + 보조 6(both 3, none 3) |
| 6 | 검색 | 벡터 기준선 → 실패 분석 후 필요 시 `pg_trgm` + RRF 하이브리드 |
| 7 | 자료 형식 | PDF 위주. 페이지 메타데이터 사용. 스캔 PDF·표 추출은 확인 대상 |
| 8 | 전공자료 동의 | 교수님 동의 받음 → 배포 서버에도 전공 색인. 동의 사실은 ADR로 기록 |
| 9 | 비용 방어 | 로그인 필수, 계정별 일일 한도, 공급사 콘솔 월 지출 한도. 게스트 계정(수강 과목 없음) 공개 |
| 10 | 대화 맥락 | 단일 턴. 멀티턴은 7주차 이후 확장 |
| 11 | 자료 갱신 | 해시 기반 폴더(→S3) 동기화, 멱등. 원본 PDF는 git에 올리지 않음 |
| 12 | HTTPS | DuckDNS 무료 도메인 + Caddy 자동 인증서 |
| 13 | 인프라 | 학교 공용 AWS 계정(서울), CloudFormation 단일 템플릿: 전용 VPC·SG·EC2·EIP·S3·IAM 역할 |

## 2. 요청 흐름

```
[React] ─ POST /api/ask (Bearer) ─▶ app/api
   ① 토큰 → User{id, courses}   ② 일일 한도 원자 증가, 초과 시 429
                                   ▼
                               app/core
   ③ classify(question) → major|academic|both|none      (LLM, 역할 모름)
   ④ plan(intent, user) → 도구 호출 목록 + 안내 문구      (순수 함수)
                                   ▼
   MCP 클라이언트 ◀─memory─▶ MCP 서버(UserContext 주입)    app/mcp  [권한 겹 1]
                                   ▼
                               app/db  scope/course SQL 필터 + 기준 점수 [권한 겹 2]
                                   ▼
   조각 0건 → 안내 / 조각 있음 → 생성 LLM → 인용 ID 검증 → 출처 조립
                                   ▼
   {answer, sources[{file,page,section}], intent, notices[]}
```

계층 `api → core → mcp → db`는 하네스 구조 테스트가 강제한다([`ARCHITECTURE.md`](../../ARCHITECTURE.md)). 권한 두 겹이 서로 다른 계층(`mcp`, `db`)에 있어 한쪽이 뚫려도 다른 쪽이 막는다.

## 3. 데이터 모델

```
users        (id, username UNIQUE, password_hash, daily_quota)
enrollments  (user_id → users, course_code, PK(user_id, course_code))
documents    (id, scope, course_code NULL, path UNIQUE, sha256)
chunks       (id, document_id → documents ON DELETE CASCADE,
              page, section NULL, ord, text, embedding vector(1536),
              scope, course_code NULL)
usage_daily  (user_id, date, count, PK(user_id, date))
```

- 역할 컬럼 없음. 전공 접근은 `enrollments` 행 존재로만 판단.
- CHECK: `(scope = 'major') = (course_code IS NOT NULL)` — documents, chunks 모두.
- 색인 2종: `chunks` 한 테이블에 `WHERE scope='major'`, `WHERE scope='academic'` 부분 HNSW 인덱스 2개.
- 조각 메타데이터 5필드 = `documents.path`(source), `page`, `section`, `scope`, `course_code`.
- 마이그레이션: Alembic. 마이그레이션이 DB 구조 SoT(`docs/sot.md` 갱신).

## 4. 인증과 권한

**로그인**: `POST /api/auth/login` → JWT(HS256, `JWT_SECRET`, 12h, payload는 `user_id`만). 비밀번호 argon2. 회원가입 API 없음, 계정은 `make users` CLI. 프론트는 `sessionStorage` + `Authorization: Bearer`.

**권한 겹 1 — `app/mcp`**: `UserContext(user_id, courses: frozenset)`로 서버 생성. `list_tools`는 `search_academic` 항상, `search_major`는 `courses`가 있을 때만. `search_major(course_code?)`는 사용자 과목과 교집합(좁히기만 가능).

**권한 겹 2 — `app/db`**: `search(query_vec, *, scope, allowed_courses)` — 기본값 없는 필수 키워드 인자.

```sql
WHERE scope = 'academic' OR (scope = 'major' AND course_code = ANY(:allowed_courses))
```

**권한 테스트 행렬 (게이트 1)** — 과목 A·B 픽스처:

| 사용자 | 기대 |
|---|---|
| A 수강생 | A 전공 + 학사만 |
| 수강 과목 없음 | 학사만, `search_major` 미노출 |
| A 수강생이 `course_code=B` | 0건 |
| MCP 우회해 `db.search` 직접 호출 | 필터 유지 |

**일일 한도**: LLM 호출 전 `INSERT … ON CONFLICT DO UPDATE SET count = count + 1 RETURNING count`. 초과 429. LLM 오류(503) 시 되돌림.

## 5. 라우터와 에이전트

- `ROUTER_MODE=workflow|agent` 설정으로 전환. 분류는 Haiku 계열, 생성·에이전트는 Sonnet 계열(생성 기본값 claude-sonnet-5-5 / effort medium, 거절 시 fallbacks "default"). 모델 ID는 설정값.
- 프롬프트는 `backend/app/core/prompts/*.md`. 평가 실행마다 프롬프트 해시 기록.

**처리 표 (`plan()`)**

| intent | 수강 과목 있음 | 없음 |
|---|---|---|
| academic | 학사 검색 | 학사 검색 |
| major | 전공 검색 | 검색 없음, "수강생 전용 자료" 안내 |
| both | 둘 다 | 학사만 + 전공 제한 안내 |
| none | 검색 없음, "범위 밖" 안내 | 동일 |

- 분류 출력이 형식 오류면 `both`로 처리(평가에서는 오답).
- 검색: 질문 1회 임베딩, top-k=5, 기준 점수 — 둘 다 설정값, 3주차 평가로 조정.
- 생성: 조각을 `[C12]` ID와 함께 제공, 인용 정규식 추출 → 검색된 ID만 인정.

**에이전트 루프 (6주차)** — 4요소를 코드에 드러낸다: ① 권한 필터된 `list_tools`로 모델 호출 ② `tool_use` → MCP `call_tool` ③ 결과·조각 ID 누적 ④ 종료: 도구 없는 응답 또는 **도구 호출 4회 상한**(상한 도달 시 누적 조각으로 강제 생성). 출처 검증 동일 적용.

## 6. 평가

- SoT: `eval/questions.yaml` (`id, question, intent, gold_sources[{file,page}], key_points[]`). 적재한 PDF를 보며 작성.
- 동결: 3주차 1차 측정 직전 해시를 `eval/FROZEN`에 기록, 테스트가 일치 검사.
- `make eval MODE=…`: 전 과목 수강 **평가 전용 계정**, effort 고정(설정값), 샘플링 파라미터 미사용 — Sonnet 5.5는 기본값 아닌 temperature에 400. 결과 `eval/runs/<날짜>-<모드>-<커밋>.jsonl`. CI에서는 돌리지 않음(지표 함수만 단위 테스트).
- 지표: 의도 정확도, recall@5, 출처 일치, none 처리(자동) / 답변 정확도(사람, `eval/grading/<run>.csv`: key_points O/X, 환각 없음 O/X). 기준은 `eval/RUBRIC.md`에 3주차 전 고정.
- `make eval-report` → `docs/generated/eval-comparison.md`.

| 시점 | 모드 | 검색 | 목적 |
|---|---|---|---|
| 3주차 | 라우터 없음(권한 내 전체 검색) | 벡터 | 기준선 |
| 4주차 | workflow | 벡터 | 의도 정확도, 라우터 효과 |
| 7주차 | workflow | 벡터/하이브리드 | 검색 개선 효과 |
| 7주차 | agent | 동일 | 워크플로우 대 에이전트 |

## 7. 운영과 배포

**AWS (학교 공용 계정, 서울)** — `infra/stack.yaml` CloudFormation 단일 스택:
- 전용 VPC, 퍼블릭 서브넷 1개. NAT·프라이빗 서브넷 없음(비용).
- 보안 그룹: 80/443 전체, 22는 본인 IP만, 5432 비공개.
- EC2 1대(앱·DB·Caddy 컨테이너) + 탄력적 IP(DuckDNS 고정).
- S3 버킷: 원본 PDF(`major/`, `academic/`), `pg_dump` 백업. 퍼블릭 액세스 차단.
- EC2 IAM 역할: 해당 버킷만 접근. 장기 액세스 키 없음(로컬은 `aws configure sso`).
- 모든 자원 태그 `Project=dept-rag-agent`, `Owner=Seonggwan`, 이름 접두사 `dept-rag-`. 스택 삭제로 내 자원만 정리.
- 권한 세트: 평소 PowerUser, IAM 역할 생성 시에만 Admin.

**컨테이너**: 멀티 스테이지 Dockerfile(프론트 빌드 → 백엔드 이미지, FastAPI가 `/` 정적 + `/api/*`). DB는 `pgvector/pgvector:pg16` + 볼륨. Caddy가 443 종단.

**비밀·자료**: `.env`는 서버에만(`chmod 600`), 이미지에 미포함. PDF는 S3 → `make ingest` 동기화.

**관측**: JSON 한 줄 로그(stdout): `request_id, user_id, intent, tool_calls, n_chunks, citation_ok, latency_ms, tokens`. 질문 원문은 기본 미기록(길이·해시만). `/health`(프로세스), `/health/ready`(DB).

**배포**: 수동 — 서버에서 `git pull && docker compose up -d --build && make smoke`. CI에 Docker 이미지 빌드 검사와 `cfn-lint` 추가. 위험 경로에 `infra/`, `Caddyfile`, 운영 compose 추가.

## 8. 만드는 순서

| 단계 | 계획 주차 | 내용 | 완료 증거 |
|---|---|---|---|
| S | 지금 | 스파이크: MCP 2.2 메모리 전송 API, pgvector 부분 HNSW·1536차원, 공용 계정 IAM 역할 생성 가능 여부 | exec-plan에 결과 기록 |
| M1 | 2 | Alembic 스키마, PDF 추출·분할·임베딩, 해시 동기화(로컬 폴더), `db.search` 필터 | 권한 테스트 행렬 통과 |
| M2 | 3 | MCP 서버 2도구, 생성·출처 검증, 평가셋 작성·동결, `make eval` | 기준선 1차 측정 |
| M3 | 4 | 로그인·JWT·CLI·일일 한도, `classify`/`plan`, `/api/ask` | 의도 정확도, 라우터 효과 |
| M4 | 5 | 화면 2종, Docker, CloudFormation, Caddy, 얇은 배포 | HTTPS URL에서 질문·답변 |
| M5 | 6 | 에이전트 루프, 통합 테스트, 권한 설계 문서 | agent 모드 평가 실행 |
| M6 | 7 | 실패 분석·하이브리드(필요 시), S3 동기화, 2차 측정 | 비교표 |
| M7 | 8 | README, 데모 영상, 결과보고서 | 제출 |

계획서 대비 조정: 배포를 5주차로 앞당김(7주차 문장은 여전히 충족), 3주차 기준선은 라우터 없이 측정.

## 9. 위험과 감수 사항

| 위험 | 대응 |
|---|---|
| 공용 계정의 다른 Admin이 S3·EC2(전공 PDF, API 키)에 접근 가능 | 서비스 전용 API 키 + 공급사 지출 한도로 피해 제한. Admin 보유자 교수님께 확인 후 ADR에 감수 사항 기록 |
| 계정 비용 조회 불가 | 작은 인스턴스, 미사용 자원 즉시 정리, 한도는 교수님께 확인 |
| SCP로 IAM 역할 생성 불가 | 스파이크 S에서 확인. 불가 시 대안 결정 필요 |
| 스캔 PDF·표 추출 품질 | M1 첫날 추출 확인, 필요 시 해당 자료 제외 또는 수동 보정 |
| 일정 지연(달력상 3주차, 2주차 작업 미착수) | M1·M2를 한 주에 병합 또는 주차 표기 조정 |

## 10. 범위 밖

멀티턴 대화, 자동 크롤링, 회원가입, 관리자 웹 화면, 자동 배포(CD), 분류·생성 공급사 교체 인터페이스, 프라이빗 서브넷·NAT.

## 11. 확인 필요 (사람)

- 교수님: 공용 계정 Admin 보유 범위, 인스턴스 크기·기간 상한, 전공자료 동의 대상 과목과 날짜(ADR 기록용)
- 대상 전공 과목 코드 확정 (M1 시작 전)
- 공급사 콘솔 월 지출 한도 설정 (Anthropic, OpenAI)
