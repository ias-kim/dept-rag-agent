import { noticeLabels } from './notices'

test('maps enrollment notice', () => {
  expect(noticeLabels(['major_requires_enrollment'])).toEqual(['전공 강의자료는 수강생만 볼 수 있어 답변에서 제외했습니다.'])
})

test('collapses tool errors and citation problems into one line each', () => {
  expect(noticeLabels(['tool_error:search_major', 'tool_error:search_academic', 'invalid_citation', 'no_citation']))
    .toEqual(['일부 자료를 검색하지 못했습니다. 답변이 불완전할 수 있습니다.', '출처를 확인하지 못한 문장이 있을 수 있습니다.'])
})

test('truncated', () => {
  expect(noticeLabels(['truncated'])).toEqual(['답변이 길어 중간에 끊겼습니다.'])
})

test('hides codes the answer text already explains, and unknown codes', () => {
  expect(noticeLabels(['out_of_scope', 'no_evidence', 'refused', 'empty', 'something_new'])).toEqual([])
})
