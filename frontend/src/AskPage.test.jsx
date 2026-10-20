import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ApiError, ask, clearToken, me } from './api'
import AskPage from './AskPage'
import { EXAMPLE_QUESTIONS } from './questions'

vi.mock('./api', async (importOriginal) => ({
  ...(await importOriginal()), ask: vi.fn(), clearToken: vi.fn(), me: vi.fn(),
}))

const full = {
  answer: '중간고사는 10월 21일입니다 [1].', intent: 'academic',
  sources: [{ file: 'academic/2026-학사일정.pdf', page: 3, section: '2학기' }], notices: [],
}

beforeEach(() => {
  me.mockResolvedValue({ username: 'kim', courses: ['AGENT', 'DB'] })
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
  expect(ask).toHaveBeenCalledWith('중간고사 언제야?')
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
  expect(ask).toHaveBeenCalledWith('첫 줄\n둘째 줄')
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
