# 학년·과목 구분과 이어지는 대화

> 마지막 갱신: 2026-11-13 · 관련 계획: `docs/exec-plans/active/2026-11-13-course-scope-chat.md`

## 1. 핵심 개념

- **후속 질문은 검색어가 아니다.** "원격이랑 로컬은 뭐가 달라?"를 그대로 임베딩하면 무엇의 원격·로컬인지 몰라 엉뚱한 공지가 잡힌다(유사도 0.15). 앞 대화를 붙인 "MCP 원격 서버와 로컬 서버의 차이"는 AGENT 자료가 0.60으로 잡힌다(2026-11-13 실측). 그래서 이력은 답변 프롬프트가 아니라 **검색 전에 질문을 다시 쓰는 데** 쓴다(`conversation.condense_question`). 답변에만 이력을 넣으면 검색은 여전히 짧은 후속 질문으로 돌고, 근거가 없으니 "찾을 수 없습니다"가 나온다.
- **이력은 클라이언트가 보낸다(서버 무상태).** 대화는 탭 안에서만 이어지고 새로고침하면 사라진다. 이력을 조작해서 바꿀 수 있는 것은 본인 질문의 검색어뿐이다. 무엇을 검색할 수 있는지(권한)는 여전히 `UserContext`와 SQL 조건이 정한다.
- **과목 선택은 좁히기만 한다.** `/api/ask`의 `course`는 서버가 DB에서 읽은 수강 과목과 대조한 뒤 `UserContext(courses={course})`로 넘긴다. 모델이 만드는 도구 인자(`course_code`)는 권한 장치가 아니다.
- **학년은 코드 카탈로그에 있다.** 학년은 DB에 없고 자료 파일명 접두어(`2-1_`)에만 있다. 그래서 마이그레이션 없이 `app/core/catalog.py` 한 곳에 과목 이름·학년·학기를 적는다. 권한과는 무관하다.

## 2. 데이터 흐름

```
[화면] AskPage.send()
  → api.ask(question, {course, history})     history = 최근 6턴 {question, answer(2000자로 자름)}
[API]  routes.ask()
  → course가 수강 과목이 아니면 403 (한도 차감 전)
  → UserContext(courses = {course} 또는 수강 전체)
  → answer_fn(question, user, session, history)
[CORE] pipeline.answer_question(history=…)
  → history가 있으면: condense_question(classify_model) → 독립 질문
       실패(거절·빈 출력·500자 초과) → 원래 질문
  → 이후는 예전과 같다: 독립 질문으로 분류(workflow)·검색·생성 / agent 루프
```

과목별 강의자료: `GET /api/courses/{code}/documents` → `db.documents.list_course_documents(allowed_courses=수강 과목)` → `[{file(파일명만), pages}]`.
학년 묶음: `GET /api/me`의 `course_details` = `catalog.sorted_by_grade(수강 과목)`.

## 3. 불변 조건과 실패 모드

권한 관련 행(과목 좁히기·강의자료 목록·이력)의 SoT는 [`design/permissions.md`](../design/permissions.md) §4·§5다. 아래 표는 그 요약과 화면·비용 쪽 조건이다.

| 조건 | 깨지면 생기는 문제 | 지키는 장치 |
|---|---|---|
| `course`는 수강 과목일 때만 쓴다 | 요청 본문으로 남의 과목 강의자료를 검색한다 (권한 사고) | `routes.ask`의 403, `test_api.py::test_ask_with_course_not_enrolled_is_forbidden_without_using_quota` |
| 과목을 고르면 같은 학생의 다른 수강 과목도 빠진다 | "이 과목에서만" 답한다는 화면 안내가 거짓이 된다 | `routes.ask`의 `frozenset({body.course})`, `test_integration.py::test_course_choice_narrows_real_pipeline_to_that_course` |
| 강의자료 목록 SQL에 수강 조건이 있다 | API 검사를 빼먹은 호출자가 남의 과목 수업 구성을 보여 준다 | `documents.py`의 `in_(allowed_courses)`, `test_course_documents.py::test_course_outside_allowed_returns_nothing_even_if_called_directly` |
| 미수강·없는 과목은 같은 403 | 응답 차이로 어떤 과목 코드가 있는지 새어 나간다 | `test_course_documents_of_other_or_unknown_course_are_forbidden_alike` |
| 이력이 없으면 재작성 호출이 없다 | 평가(단일 질문)의 호출 수·비용이 이전 실행과 달라져 비교가 무효가 된다 | `test_pipeline.py::test_no_history_means_no_rewrite_call` |
| 재작성이 `end_turn`으로 끝났을 때만 쓴다 | 거절 내용을 읽거나, max_tokens로 끊긴 반쪽 문장이 검색어가 된다 | `conversation.condense_question`, `test_truncated_output_falls_back_to_original_question` |
| 재작성 결과는 500자 이하 | 긴 검색어의 임베딩이 4xx로 실패 → 500, 한도도 못 돌려받는다 | `CONDENSED_MAX_CHARS`, `test_conversation.py::test_overlong_output_falls_back_to_original_question` |
| 이력 상한(6턴·답변 2000자)이 화면과 서버에서 같다 | 대화가 길어지면 다음 질문 전체가 422로 거절된다 | `questions.js`·`routes.py` 상수, `AskPage.test.jsx` "history is trimmed to the server limits" |
| 과목을 바꾸면 대화를 비운다 | 재작성이 이전 과목 주제로 끌려가 엉뚱한 검색어가 된다 | `AskPage.selectCourse`, "switching course starts a new conversation" |
| 답을 기다리는 중에는 과목·새 대화 버튼이 잠긴다 | 늦게 온 이전 과목 답이 새 대화에 붙고, 다음 질문 이력으로 새 과목과 함께 나간다 | `CourseNav locked`, "course and new-conversation buttons are locked while an answer is pending" |
| 사이드바는 1~3학년 칸을 항상 보인다(수강 없으면 "수강 과목 없음") | 학년 칸이 사라지면 학생이 "이 학년 과목이 빠졌나?"와 "안 듣는다"를 구분 못 한다 | `AskPage.groupByGrade`, "sidebar lists every grade in order…" |
| 실패한 질문은 이력에 넣지 않는다 | 답 없는 턴이 맥락으로 들어가 재작성이 흔들린다 | "failed question is not added to history" |

외부 요인: 재작성 호출에서 공급사 장애(5xx·429·연결 실패)가 나면 다른 LLM 호출과 같이 `UpstreamError` → 503 + 한도 환불이다(`deps.get_answer_fn`, `test_integration.py::test_rewrite_outage_returns_503_and_refunds` — 재작성에서 예외를 삼키면 실패함을 변이로 확인).

화면: 답을 기다리는 동안 이어 쓴 글은 답이 와도 지우지 않는다(보낸 질문과 같을 때만 비움). 강의자료 목록이 401이면 로그인 화면으로 보낸다.

## 4. 다음 수정

- 대화 서버 저장(`conversations` 테이블)과 새로고침 후 이어 보기. 지금은 탭 메모리에만 있다.
- 평가셋에 후속 질문 문항(2턴)을 넣어 재작성 효과를 숫자로 잰다. 지금 근거는 수동 실측 한 건이다.
- 강의자료 원문 열기(파일 내려받기)는 범위 밖이다.

## 5. 업데이트 시 주의점

- `prompts/condense.md`를 고치면 재작성 결과가 바뀐다. 평가 meta에는 아직 해시를 남기지 않는다(평가는 이력 없이 돌기 때문). 후속 질문 평가를 넣을 때 `condense_prompt_hash()`를 meta에 추가한다.
- `answer.md`·`agent.md`는 이번 변경에서 손대지 않았다. 고치면 평가 해시가 바뀐다.
- 과목 폴더(`data/major/<코드>`)를 새로 만들면 `catalog.py`에 한 줄 추가한다. 빠뜨리면 화면에 코드만 "기타" 아래 보인다.
- API 모양을 바꿨으면 `make generate`(OpenAPI 스냅샷).

## 파일 위치

| 파일 | 역할 |
|---|---|
| `backend/app/core/catalog.py` | 과목 코드 → 이름·학년·학기 |
| `backend/app/core/conversation.py`, `prompts/condense.md` | 후속 질문 재작성 |
| `backend/app/db/documents.py` | 과목별 강의자료 목록(수강 조건 SQL) |
| `backend/app/api/routes.py` | `course`·`history` 검증, `/api/courses/{code}/documents`, `/api/me` 학년 정보 |
| `frontend/src/AskPage.jsx` | 왼쪽 사이드바(1~3학년 칸과 수강 과목, 전체 과목), 강의자료 패널, 대화 스레드·새 대화 |
