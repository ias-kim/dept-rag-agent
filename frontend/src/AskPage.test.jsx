import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ApiError, ask, clearToken, courseDocuments, me } from './api'
import AskPage from './AskPage'
import { EXAMPLE_QUESTIONS, HISTORY_ANSWER_MAX_CHARS, HISTORY_MAX_TURNS } from './questions'

vi.mock('./api', async (importOriginal) => ({
  ...(await importOriginal()), ask: vi.fn(), clearToken: vi.fn(), courseDocuments: vi.fn(), me: vi.fn(),
}))

const full = {
  answer: '중간고사는 10월 21일입니다 [1].', intent: 'academic',
  sources: [{ file: 'academic/2026-학사일정.pdf', page: 3, section: '2학기' }], notices: [],
}

const PROFILE = {
  username: 'kim', courses: ['AGENT', 'DB'],
  course_details: [
    { code: 'AGENT', name: 'AI 에이전트·MCP', grade: 3, semesters: ['3-1', '3-2'] },
    { code: 'DB', name: '데이터베이스', grade: 2, semesters: ['2-2'] },
  ],
}

beforeEach(() => {
  me.mockResolvedValue(PROFILE)
  courseDocuments.mockResolvedValue([{ file: '3-1_mcp.pdf', pages: 20 }, { file: '3-2_Docker.pdf', pages: 81 }])
})

async function submit(user, text = '중간고사 언제야?') {
  await user.type(screen.getByLabelText('질문'), text)
  await user.click(screen.getByRole('button', { name: '질문하기' }))
}

function setup(onLogout = vi.fn()) {
  const user = userEvent.setup()
  render(<AskPage onLogout={onLogout} />)
  return { user, onLogout }
}

test('explains the service up front', () => {
  setup()
  expect(screen.getByRole('heading', { name: '무엇이든 물어보세요' })).toBeInTheDocument()
  expect(screen.getByText(/근거와 함께 답해 드립니다/)).toBeInTheDocument()
})

test('shows username and enrolled courses', async () => {
  setup()
  expect(await screen.findByText('AGENT · DB 수강')).toBeInTheDocument()
  expect(screen.getByText('kim')).toBeInTheDocument()
})

test('guest sees that only academic material is searched', async () => {
  me.mockResolvedValue({ username: 'guest', courses: [] })
  setup()
  expect(await screen.findByText('게스트 · 학사 자료만')).toBeInTheDocument()
})

test('failed profile lookup hides the badge but still allows asking', async () => {
  me.mockRejectedValue(new ApiError(0, 'x'))
  ask.mockResolvedValue(full)
  const { user } = setup()
  await submit(user)
  expect(await screen.findByRole('article')).toHaveTextContent('중간고사는 10월 21일입니다')
  expect(screen.queryByText(/수강$/)).toBeNull()
})

test('expired token at page load returns to login before typing', async () => {
  me.mockRejectedValue(new ApiError(401, '로그인이 필요합니다'))
  const { onLogout } = setup()
  await vi.waitFor(() => expect(onLogout).toHaveBeenCalledWith('expired'))
})

test('example question fills the input', async () => {
  const { user } = setup()
  await user.click(screen.getByRole('button', { name: EXAMPLE_QUESTIONS[0] }))
  expect(screen.getByLabelText('질문')).toHaveValue(EXAMPLE_QUESTIONS[0])
  expect(ask).not.toHaveBeenCalled()
})

test('shows answer and numbered source with page', async () => {
  ask.mockResolvedValue(full)
  const { user } = setup()
  await submit(user)
  expect(await screen.findByRole('article')).toHaveTextContent('중간고사는 10월 21일입니다')
  expect(screen.getByRole('heading', { name: '이 답변의 근거 자료' })).toBeInTheDocument()
  const item = screen.getByRole('listitem')
  expect(item).toHaveTextContent('2026-학사일정.pdf')
  expect(item).toHaveTextContent('2학기')
  expect(item).toHaveTextContent('3쪽')
  expect(within(item).getByTitle('academic/2026-학사일정.pdf')).toBeInTheDocument()
  expect(ask).toHaveBeenCalledWith('중간고사 언제야?', { course: null, history: [] })
})

test('sources keep server order so [n] matches', async () => {
  ask.mockResolvedValue({ ...full, sources: [
    { file: 'b.pdf', page: 9, section: null }, { file: 'a.pdf', page: 1, section: null },
  ] })
  const { user } = setup()
  await submit(user)
  const items = await screen.findAllByRole('listitem')
  expect(items.map((li) => li.textContent)).toEqual([
    expect.stringContaining('b.pdf'), expect.stringContaining('a.pdf'),
  ])
})

test('omits null section', async () => {
  ask.mockResolvedValue({ ...full, sources: [{ file: 'x.pdf', page: 1, section: null }] })
  const { user } = setup()
  await submit(user)
  const item = await screen.findByRole('listitem')
  expect(item).toHaveTextContent('x.pdf')
  expect(item).toHaveTextContent('1쪽')
  expect(item.textContent).not.toContain('null')
})

test('renders answer without sources', async () => {
  ask.mockResolvedValue({ answer: '학과 자료 범위 밖의 질문입니다.', sources: [], intent: 'none', notices: ['out_of_scope'] })
  const { user } = setup()
  await submit(user)
  expect(await screen.findByRole('article')).toHaveTextContent('학과 자료 범위 밖의 질문입니다.')
  expect(screen.queryByRole('heading', { name: '이 답변의 근거 자료' })).toBeNull()
  expect(screen.queryByRole('status')).toBeNull()
})

test('shows mapped notices only', async () => {
  ask.mockResolvedValue({ ...full, notices: ['major_requires_enrollment', 'tool_error:search_major'] })
  const { user } = setup()
  await submit(user)
  const status = await screen.findByRole('status')
  expect(status).toHaveTextContent('전공 강의자료는 수강생만 볼 수 있어 답변에서 제외했습니다.')
  expect(status).toHaveTextContent('일부 자료를 검색하지 못했습니다.')
  expect(document.body.textContent).not.toContain('tool_error')
})

test('disables submit and shows skeleton while waiting', async () => {
  ask.mockReturnValue(new Promise(() => {}))
  const { user } = setup()
  await submit(user)
  const button = screen.getByRole('button', { name: /답변을 만드는 중/ })
  expect(button).toBeDisabled()
  expect(screen.getByLabelText('답변을 불러오는 중')).toBeInTheDocument()
  await user.click(button)
  await user.click(screen.getByLabelText('질문')) // 포커스를 입력창으로 — 그래야 Enter가 handleKeyDown을 거친다
  await user.keyboard('{Enter}')
  expect(ask).toHaveBeenCalledTimes(1)
})

test('Enter sends, Shift+Enter adds a line', async () => {
  ask.mockResolvedValue(full)
  const { user } = setup()
  await user.type(screen.getByLabelText('질문'), '첫 줄{Shift>}{Enter}{/Shift}둘째 줄')
  expect(ask).not.toHaveBeenCalled()
  await user.keyboard('{Enter}')
  expect(ask).toHaveBeenCalledWith('첫 줄\n둘째 줄', { course: null, history: [] })
})

test('blank or too long question cannot be sent', async () => {
  const { user } = setup()
  await user.type(screen.getByLabelText('질문'), '   ')
  expect(screen.getByRole('button', { name: '질문하기' })).toBeDisabled()
  expect(screen.getByLabelText('질문')).toHaveAttribute('maxLength', '500')
})

test('expired token returns to login', async () => {
  ask.mockRejectedValue(new ApiError(401, '로그인이 필요합니다'))
  const { user, onLogout } = setup()
  await submit(user)
  await vi.waitFor(() => expect(onLogout).toHaveBeenCalledWith('expired'))
})

test('quota error shows server message', async () => {
  ask.mockRejectedValue(new ApiError(429, '오늘 질문 한도를 모두 사용했습니다'))
  const { user } = setup()
  await submit(user)
  expect(await screen.findByRole('alert')).toHaveTextContent('오늘 질문 한도를 모두 사용했습니다')
})

test('logout clears token', async () => {
  const { user, onLogout } = setup()
  await user.click(screen.getByRole('button', { name: '로그아웃' }))
  expect(clearToken).toHaveBeenCalled()
  expect(onLogout).toHaveBeenCalledWith()
})

test('citation markers become numbered badges', async () => {
  ask.mockResolvedValue({ ...full, answer: 'Host는 판단합니다 [1]. Server는 기능을 줍니다 [1][2].', sources: [
    { file: 'a.pdf', page: 4, section: null }, { file: 'a.pdf', page: 11, section: null },
  ] })
  const { user } = setup()
  await submit(user)
  const article = await screen.findByRole('article')
  const badges = [...article.querySelectorAll('.cite')]
  // 화면에는 숫자만 보이지만, 숨김 글자 "출처 "가 있어야 스크린리더가 맥락 있게 읽는다
  expect(badges.map((b) => b.textContent)).toEqual(['출처 1', '출처 1', '출처 2'])
  badges.forEach((b) => expect(b.querySelector('.sr-only')).toHaveTextContent('출처'))
  expect(article.querySelector('.answer-text').textContent).not.toContain('[')
})

test('**bold** in the answer renders as strong text, not asterisks', async () => {
  ask.mockResolvedValue({ ...full, answer: '- **Host**: 판단합니다 [1]\n- **Server [1]** 기능을 줍니다' })
  const { user } = setup()
  await submit(user)
  const text = (await screen.findByRole('article')).querySelector('.answer-text')
  const strongs = [...text.querySelectorAll('strong')]
  expect(strongs.map((s) => s.textContent)).toEqual(['Host', 'Server 출처 1'])
  // 굵은 글씨 안의 인용도 배지가 되어야 출처 번호가 사라지지 않는다
  expect(strongs[1].querySelector('.cite')).toHaveTextContent('1')
  expect(text.querySelectorAll('.cite')).toHaveLength(2)
  expect(text.textContent).not.toContain('**')
})

test.each([
  ['def w(*args, **kwargs): return f(*args, **kwargs)'],
  ['2**3 + 3**2'],
])('paired ** that is not emphasis stays literal: %s', async (code) => {
  // 짝만 맞으면 굵게로 바꾸면 ** 가 사라져 코드와 수식이 다른 내용으로 읽힌다
  ask.mockResolvedValue({ ...full, answer: code })
  const { user } = setup()
  await submit(user)
  const text = (await screen.findByRole('article')).querySelector('.answer-text')
  expect(text.querySelector('strong')).toBeNull()
  expect(text.textContent).toBe(code)
})

test('emphasis attached to Korean text is still bold', async () => {
  ask.mockResolvedValue({ ...full, answer: '**굵게**입니다 [1]' })
  const { user } = setup()
  await submit(user)
  const text = (await screen.findByRole('article')).querySelector('.answer-text')
  expect(text.querySelector('strong')).toHaveTextContent('굵게')
})

test('unmatched ** stays as literal text', async () => {
  ask.mockResolvedValue({ ...full, answer: '2**3은 8입니다 [1].' })
  const { user } = setup()
  await submit(user)
  const text = (await screen.findByRole('article')).querySelector('.answer-text')
  expect(text.querySelector('strong')).toBeNull()
  expect(text.textContent).toContain('2**3은 8입니다')
})

test('enrollment notice is not repeated when the answer itself says so', async () => {
  // 수강생 전용 질문에 게스트가 받는 답은 본문이 이미 같은 안내다 — 출처 없이 같은 말이 두 번 보인다
  ask.mockResolvedValue({ answer: '전공 강의자료는 해당 과목 수강생만 검색할 수 있습니다.', sources: [], intent: 'major',
    notices: ['major_requires_enrollment'] })
  const { user } = setup()
  await submit(user)
  await screen.findByRole('article')
  expect(screen.queryByRole('status')).toBeNull()
})

test('enrollment notice stays when a both-intent answer found nothing', async () => {
  // 게스트의 both 질문은 학사만 찾는다 — 그마저 못 찾으면 본문엔 수강 얘기가 없으니 안내가 있어야 전공 자료가 빠진 걸 안다
  ask.mockResolvedValue({ answer: '관련 자료를 찾지 못했습니다. 질문을 조금 더 구체적으로 해 주세요.', sources: [], intent: 'both',
    notices: ['major_requires_enrollment', 'no_evidence'] })
  const { user } = setup()
  await submit(user)
  expect(await screen.findByRole('status')).toHaveTextContent('전공 강의자료는 수강생만 볼 수 있어 답변에서 제외했습니다.')
})

test('Enter during Hangul composition does not send', async () => {
  const { user } = setup()
  await user.type(screen.getByLabelText('질문'), '안녕')
  fireEvent.keyDown(screen.getByLabelText('질문'), { key: 'Enter', isComposing: true })
  expect(ask).not.toHaveBeenCalled()
})

test('composition-confirm Enter with keyCode 229 does not send', async () => {
  // Safari는 조합을 확정하는 Enter를 isComposing=false, keyCode=229로 보낸다
  const { user } = setup()
  await user.type(screen.getByLabelText('질문'), '안녕')
  fireEvent.keyDown(screen.getByLabelText('질문'), { key: 'Enter', keyCode: 229 })
  expect(ask).not.toHaveBeenCalled()
})


// ── 학년·과목 구분, 과목별 강의자료 ──

test('sidebar lists every grade in order with enrolled courses under each', async () => {
  setup()
  const sidebar = screen.getByRole('complementary', { name: '과목 선택' })
  const nav = await within(sidebar).findByRole('navigation', { name: '내 과목' })
  const headings = within(nav).getAllByRole('heading').map((h) => h.textContent)
  // 학년 숫자만 이름에 들어가게 한다 — 수강 과목 수 표시는 heading 밖의 배지로
  expect(headings).toEqual(['1학년', '2학년', '3학년'])
  const grade1 = within(nav).getByRole('region', { name: '1학년' })
  expect(grade1).toHaveTextContent('수강 과목 없음')
  const grade3 = within(nav).getByRole('region', { name: '3학년' })
  const agent = within(grade3).getByRole('button', { name: /AI 에이전트·MCP/ })
  expect(agent).toHaveTextContent('AGENT')
  expect(agent).toHaveTextContent('3-1 · 3-2학기')
  expect(within(nav).getByRole('region', { name: '2학년' })).toHaveTextContent('데이터베이스')
  expect(within(nav).getByRole('button', { name: /전체 과목/ })).toHaveAttribute('aria-pressed', 'true')
})

test('selected course is highlighted in the sidebar', async () => {
  const { user } = setup()
  const db = await screen.findByRole('button', { name: /데이터베이스/ })
  await user.click(db)
  expect(db).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByRole('button', { name: /전체 과목/ })).toHaveAttribute('aria-pressed', 'false')
})

test('course without grade is shown under 기타 by its code', async () => {
  me.mockResolvedValue({ username: 'kim', courses: ['NEW999'],
    course_details: [{ code: 'NEW999', name: 'NEW999', grade: null, semesters: [] }] })
  setup()
  const nav = await screen.findByRole('navigation', { name: '내 과목' })
  expect(within(nav).getByRole('region', { name: '기타' })).toBeInTheDocument()
  expect(within(nav).getByRole('button', { name: /NEW999/ })).toBeInTheDocument()
})

test('guest sidebar explains that only academic notices are searched', async () => {
  me.mockResolvedValue({ username: 'guest', courses: [], course_details: [] })
  setup()
  const sidebar = screen.getByRole('complementary', { name: '과목 선택' })
  expect(await within(sidebar).findByText(/수강 중인 전공 과목이 없어 학사 공지만 검색합니다/)).toBeInTheDocument()
  expect(screen.queryByRole('navigation', { name: '내 과목' })).toBeNull()
})

test('choosing a course lists its lecture materials and scopes the next question', async () => {
  ask.mockResolvedValue(full)
  const { user } = setup()
  await user.click(await screen.findByRole('button', { name: /AI 에이전트·MCP/ }))
  expect(courseDocuments).toHaveBeenCalledWith('AGENT')
  const materials = await screen.findByRole('region', { name: 'AI 에이전트·MCP 강의자료' })
  expect(within(materials).getAllByRole('listitem').map((li) => li.textContent)).toEqual([
    expect.stringContaining('3-1_mcp.pdf'), expect.stringContaining('3-2_Docker.pdf'),
  ])
  expect(materials).toHaveTextContent('81쪽')
  await submit(user, 'MCP가 뭐야?')
  expect(ask).toHaveBeenCalledWith('MCP가 뭐야?', { course: 'AGENT', history: [] })
})

test('choosing 전체 again searches every enrolled course', async () => {
  ask.mockResolvedValue(full)
  const { user } = setup()
  await user.click(await screen.findByRole('button', { name: /데이터베이스/ }))
  await user.click(screen.getByRole('button', { name: /전체 과목/ }))
  expect(screen.queryByRole('region', { name: /강의자료/ })).toBeNull()
  await submit(user)
  expect(ask).toHaveBeenCalledWith('중간고사 언제야?', { course: null, history: [] })
})

test('materials load failure is shown without blocking questions', async () => {
  courseDocuments.mockRejectedValue(new ApiError(0, '서버에 연결할 수 없습니다.'))
  ask.mockResolvedValue(full)
  const { user } = setup()
  await user.click(await screen.findByRole('button', { name: /AI 에이전트·MCP/ }))
  expect(await screen.findByText(/강의자료 목록을 불러오지 못했습니다/)).toBeInTheDocument()
  await submit(user)
  expect(ask).toHaveBeenCalled()
})

// ── 이어지는 대화 ──

test('follow-up question sends earlier turns as history and keeps both answers on screen', async () => {
  ask.mockResolvedValueOnce({ ...full, answer: 'Host는 앱입니다 [1].' })
    .mockResolvedValueOnce({ ...full, answer: '원격 서버는 HTTP로 붙습니다 [1].' })
  const { user } = setup()
  await submit(user, 'MCP Host가 뭐야?')
  await screen.findByText(/Host는 앱입니다/)
  expect(screen.getByLabelText('질문')).toHaveValue('') // 다음 질문을 바로 쓸 수 있게 비운다
  await submit(user, '원격이랑 로컬은 뭐가 달라?')
  await screen.findByText(/원격 서버는 HTTP로 붙습니다/)
  expect(ask).toHaveBeenLastCalledWith('원격이랑 로컬은 뭐가 달라?', {
    course: null, history: [{ question: 'MCP Host가 뭐야?', answer: 'Host는 앱입니다 [1].' }],
  })
  const turns = screen.getAllByRole('article')
  expect(turns).toHaveLength(2)
  expect(turns[0]).toHaveTextContent('MCP Host가 뭐야?')
  expect(turns[1]).toHaveTextContent('원격이랑 로컬은 뭐가 달라?')
})

test('new conversation clears the thread and history', async () => {
  ask.mockResolvedValue(full)
  const { user } = setup()
  await submit(user, '첫 질문')
  await screen.findByRole('article')
  await user.click(screen.getByRole('button', { name: '새 대화' }))
  expect(screen.queryByRole('article')).toBeNull()
  await submit(user, '두 번째')
  expect(ask).toHaveBeenLastCalledWith('두 번째', { course: null, history: [] })
})

test('switching course starts a new conversation', async () => {
  // 다른 과목 대화를 이어 붙이면 재작성된 검색어가 이전 과목 주제로 끌려간다
  ask.mockResolvedValue(full)
  const { user } = setup()
  await submit(user, '첫 질문')
  await screen.findByRole('article')
  await user.click(screen.getByRole('button', { name: /데이터베이스/ }))
  expect(screen.queryByRole('article')).toBeNull()
  await submit(user, '외래키가 뭐야?')
  expect(ask).toHaveBeenLastCalledWith('외래키가 뭐야?', { course: 'DB', history: [] })
})

test('history is trimmed to the server limits', async () => {
  // 서버 상한을 넘기면 다음 질문 전체가 422로 거절된다
  ask.mockResolvedValue({ ...full, answer: '가'.repeat(HISTORY_ANSWER_MAX_CHARS + 50) })
  const { user } = setup()
  for (let i = 0; i <= HISTORY_MAX_TURNS; i += 1) {
    await submit(user, `질문${i}`)
    await vi.waitFor(() => expect(ask).toHaveBeenCalledTimes(i + 1))
    await vi.waitFor(() => expect(screen.getByLabelText('질문')).toHaveValue(''))
  }
  await submit(user, '마지막')
  const { history } = ask.mock.lastCall[1]
  expect(history).toHaveLength(HISTORY_MAX_TURNS)
  expect(history[0].question).toBe('질문1')
  expect(history.every((t) => t.answer.length === HISTORY_ANSWER_MAX_CHARS)).toBe(true)
})

test('failed question is not added to history', async () => {
  ask.mockRejectedValueOnce(new ApiError(503, '답변 서비스가 잠시 응답하지 않습니다')).mockResolvedValue(full)
  const { user } = setup()
  await submit(user, '실패할 질문')
  await screen.findByRole('alert')
  await user.clear(screen.getByLabelText('질문'))
  await submit(user, '다시')
  expect(ask).toHaveBeenLastCalledWith('다시', { course: null, history: [] })
})

test('course and new-conversation buttons are locked while an answer is pending', async () => {
  // 기다리는 중에 과목을 바꾸면 늦게 온 이전 과목 답이 새 대화에 붙고, 다음 질문의 이력으로 새 과목과 함께 나간다
  ask.mockResolvedValueOnce(full).mockReturnValueOnce(new Promise(() => {}))
  const { user } = setup()
  await submit(user, '첫 질문')
  await screen.findByRole('article')
  await submit(user, '두 번째')
  const nav = screen.getByRole('navigation', { name: '내 과목' })
  within(nav).getAllByRole('button').forEach((b) => expect(b).toBeDisabled())
  expect(screen.getByRole('button', { name: '새 대화' })).toBeDisabled()
})
