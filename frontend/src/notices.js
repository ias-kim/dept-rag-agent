// 서버 공지 코드 → 학생에게 보일 문구.
// 코드 원천: backend/app/core/router.py(major_requires_enrollment·out_of_scope), pipeline.py(tool_error:<도구>),
// answer.py(no_evidence·refused·empty·invalid_citation·no_citation·truncated).
// 서버에 코드가 늘었는데 여기 빠지면 그 안내가 숨겨질 뿐 화면이 깨지지는 않는다 — 코드 원문은 절대 그대로 보이지 않는다.

const LABELS = {
  major_requires_enrollment: '전공 강의자료는 수강생만 볼 수 있어 답변에서 제외했습니다.',
  invalid_citation: '출처를 확인하지 못한 문장이 있을 수 있습니다.',
  no_citation: '출처를 확인하지 못한 문장이 있을 수 있습니다.',
  truncated: '답변이 길어 중간에 끊겼습니다.',
}
const TOOL_ERROR_PREFIX = 'tool_error:'
const TOOL_ERROR_LABEL = '일부 자료를 검색하지 못했습니다. 답변이 불완전할 수 있습니다.'
// out_of_scope·no_evidence·refused·empty는 답변 본문이 이미 같은 말을 하므로 LABELS에 두지 않는다

export function noticeLabels(codes) {
  const labels = codes.map((code) => (code.startsWith(TOOL_ERROR_PREFIX) ? TOOL_ERROR_LABEL : LABELS[code]))
  return [...new Set(labels.filter(Boolean))]
}
