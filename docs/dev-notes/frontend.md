# 화면(프론트엔드) — 5주차 로그인·질문 화면

> 마지막 갱신: 2026-10-20 · 계획: [`docs/exec-plans/active/2026-10-20-m4a-frontend.md`](../exec-plans/active/2026-10-20-m4a-frontend.md) · 설계 §2·§4·§7

## 1. 핵심 개념

**서버 공지 코드는 화면 문구로 바꿔서 보인다.** 서버는 `notices`에 기계용 코드(`major_requires_enrollment`, `tool_error:search_major` …)를 담는다. 학생에게 코드 원문을 보이면 안 되므로 `src/notices.js`의 `noticeLabels`가 문구로 바꾸고, 모르는 코드와 답변 본문이 이미 설명하는 코드(`out_of_scope`·`no_evidence`·`refused`·`empty`)는 숨긴다.

## 2. 데이터 흐름

(Task 2~4에서 채움)

## 3. 불변 조건과 실패 모드

| 조건 | 깨지면 생기는 문제 | 지키는 장치 |
|---|---|---|
| 토큰은 `sessionStorage`(`dept-rag-token`)에만 둔다 | `localStorage`로 바꾸면 공용 PC에서 탭을 닫아도 다음 사람이 로그인된 채로 질문한다(한도·권한 도용) | `api.js` `TOKEN_KEY`, `api.test.js` |
| 오류 문구는 서버 `detail` 문자열 그대로 | 429를 화면이 "한도 소진"으로 단정하면 로그인 시도 과다 상황에 틀린 안내가 나간다 | `api.js` `errorMessage`, `api.test.js::string detail becomes message` |
| 401이면 토큰을 지운다 | 12시간 지나 만료된 토큰을 계속 보내며 같은 오류만 반복한다 | `api.js` `request`, `api.test.js::ask 401 clears token` |
| JSON이 아닌 오류 본문(프록시 502 HTML)에서도 깨지지 않는다 | `JSON.parse` 예외로 화면 전체가 멈춘다 | `api.js` 본문 파싱 실패 허용, `api.test.js::non-json error body…` |
| 공지 코드 원문은 화면에 나가지 않는다 | `tool_error:search_major` 같은 내부 이름이 학생에게 보인다 | `notices.js` 기본값 숨김, `notices.test.js` |

## 4. 다음 수정

## 5. 업데이트 시 주의점

- 서버에 공지 코드를 추가하면 `frontend/src/notices.js`에도 추가한다. 빠뜨리면 그 안내가 조용히 숨겨진다.
- 프론트 테스트는 `make test`(= `test-py` + `test-fe`)에 포함된다. CI도 `make check`로 같이 돈다.
