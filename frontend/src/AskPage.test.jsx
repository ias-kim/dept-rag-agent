import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ApiError, ask, clearToken } from './api'
import AskPage from './AskPage'

vi.mock('./api', async (importOriginal) => ({ ...(await importOriginal()), ask: vi.fn(), clearToken: vi.fn() }))

const full = {
  answer: '중간고사는 10월 21일입니다 [1].', intent: 'academic',
  sources: [{ file: 'academic/2026-학사일정.pdf', page: 3, section: '2학기' }], notices: [],
}

async function submit(user, text = '중간고사 언제야?') {
  await user.type(screen.getByLabelText('질문'), text)
  await user.click(screen.getByRole('button', { name: '질문하기' }))
}

function setup(onLogout = vi.fn()) {
  const user = userEvent.setup()
  render(<AskPage onLogout={onLogout} />)
  return { user, onLogout }
}

test('shows answer and numbered source', async () => {
  ask.mockResolvedValue(full)
  const { user } = setup()
  await submit(user)
  expect(await screen.findByText('중간고사는 10월 21일입니다 [1].')).toBeInTheDocument()
  const item = screen.getByRole('listitem')
  expect(item).toHaveTextContent('2026-학사일정.pdf · p.3 · 2학기')
  expect(item.querySelector('[title]')).toHaveAttribute('title', 'academic/2026-학사일정.pdf')
  expect(ask).toHaveBeenCalledWith('중간고사 언제야?')
})

test('omits null section', async () => {
  ask.mockResolvedValue({ ...full, sources: [{ file: 'x.pdf', page: 1, section: null }] })
  const { user } = setup()
  await submit(user)
  const item = await screen.findByRole('listitem')
  expect(item.textContent).toBe('x.pdf · p.1')
})

test('renders answer without sources', async () => {
  ask.mockResolvedValue({ answer: '학과 자료 범위 밖의 질문입니다.', sources: [], intent: 'none', notices: ['out_of_scope'] })
  const { user } = setup()
  await submit(user)
  expect(await screen.findByText('학과 자료 범위 밖의 질문입니다.')).toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: '출처' })).toBeNull()
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

test('disables submit while waiting', async () => {
  ask.mockReturnValue(new Promise(() => {}))
  const { user } = setup()
  await submit(user)
  const button = screen.getByRole('button', { name: /답변을 만드는 중/ })
  expect(button).toBeDisabled()
  await user.click(button)
  expect(ask).toHaveBeenCalledTimes(1)
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
