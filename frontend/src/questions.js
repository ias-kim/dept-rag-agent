// 원천은 서버 QUESTION_MAX_CHARS (backend/app/api/routes.py). 서버 값만 바꾸면 긴 질문이 422로 거절된다
export const QUESTION_MAX_CHARS = 500
// 처음 온 학생이 "무엇을 물어볼 수 있는지" 알게 하는 예시 — 학사·전공 자료가 모두 있다는 것을 보여 준다.
// 적재된 자료로 답이 나오는 질문만 둔다(2026-11-01 workflow·agent 둘 다 확인). 자료에 없으면 시연 첫 화면이 "못 찾음"이 된다
export const EXAMPLE_QUESTIONS = ['2학년 면접 일본어 특강은 언제 어디서 해?', 'MCP에서 Host, Client, Server는 각각 무슨 역할이야?', '외래키(foreign key)가 뭐야?']
