// 원천은 서버 QUESTION_MAX_CHARS (backend/app/api/routes.py). 서버 값만 바꾸면 긴 질문이 422로 거절된다
export const QUESTION_MAX_CHARS = 500
// 처음 온 학생이 "무엇을 물어볼 수 있는지" 알게 하는 예시 — 학사·전공 자료가 모두 있다는 것을 보여 준다
export const EXAMPLE_QUESTIONS = ['2학기 중간고사 기간이 언제야?', 'MCP에서 Host, Client, Server는 각각 무슨 역할이야?', '트랜잭션의 ACID 성질을 설명해줘']
