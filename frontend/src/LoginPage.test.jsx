import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ApiError, login } from './api'
import LoginPage from './LoginPage'

vi.mock('./api', async (importOriginal) => ({ ...(await importOriginal()), login: vi.fn() }))

async function fill(user) {
  await user.type(screen.getByLabelText('아이디'), 'kim')
  await user.type(screen.getByLabelText('비밀번호'), 'pw')
}

test('submits credentials and calls onLoggedIn', async () => {
  login.mockResolvedValue()
  const onLoggedIn = vi.fn()
  const user = userEvent.setup()
  render(<LoginPage onLoggedIn={onLoggedIn} />)
  await fill(user)
  await user.click(screen.getByRole('button', { name: '로그인' }))
  expect(login).toHaveBeenCalledWith('kim', 'pw')
  expect(onLoggedIn).toHaveBeenCalledTimes(1)
})

test('shows server message on failure', async () => {
  login.mockRejectedValue(new ApiError(401, '아이디 또는 비밀번호가 올바르지 않습니다'))
  const onLoggedIn = vi.fn()
  const user = userEvent.setup()
  render(<LoginPage onLoggedIn={onLoggedIn} />)
  await fill(user)
  await user.click(screen.getByRole('button', { name: '로그인' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('아이디 또는 비밀번호가 올바르지 않습니다')
  expect(onLoggedIn).not.toHaveBeenCalled()
})

test('button disabled while pending and when fields empty', async () => {
  login.mockReturnValue(new Promise(() => {}))
  const user = userEvent.setup()
  render(<LoginPage onLoggedIn={vi.fn()} />)
  const button = screen.getByRole('button', { name: '로그인' })
  expect(button).toBeDisabled()
  await fill(user)
  expect(button).toBeEnabled()
  await user.click(button)
  expect(button).toBeDisabled()
})

test('shows notice prop', () => {
  render(<LoginPage onLoggedIn={vi.fn()} notice="로그인이 만료되었습니다. 다시 로그인해 주세요." />)
  expect(screen.getByText('로그인이 만료되었습니다. 다시 로그인해 주세요.')).toBeInTheDocument()
})
