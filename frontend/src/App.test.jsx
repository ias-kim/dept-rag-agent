import { render, screen } from '@testing-library/react'
import App from './App'
import { TOKEN_KEY } from './api'

test('shows login when no token', () => {
  render(<App />)
  expect(screen.getByRole('heading', { name: '로그인' })).toBeInTheDocument()
})

test('shows ask page when token exists', () => {
  sessionStorage.setItem(TOKEN_KEY, 't1')
  vi.spyOn(globalThis, 'fetch').mockReturnValue(new Promise(() => {})) // /api/me — 응답을 기다리는 상태로 둔다
  render(<App />)
  expect(screen.getByRole('heading', { name: '무엇이든 물어보세요' })).toBeInTheDocument()
})

test('expired token at load lands on login with the expiry notice', async () => {
  sessionStorage.setItem(TOKEN_KEY, 'old')
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: '로그인이 필요합니다' }), { status: 401 }))
  render(<App />)
  expect(await screen.findByText('로그인이 만료되었습니다. 다시 로그인해 주세요.')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '로그인' })).toBeInTheDocument()
})
