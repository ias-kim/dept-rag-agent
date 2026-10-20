import { render, screen } from '@testing-library/react'
import App from './App'
import { TOKEN_KEY } from './api'

test('shows login when no token', () => {
  render(<App />)
  expect(screen.getByRole('heading', { name: '로그인' })).toBeInTheDocument()
})

test('shows ask page when token exists', () => {
  sessionStorage.setItem(TOKEN_KEY, 't1')
  render(<App />)
  expect(screen.getByRole('heading', { name: '질문하기' })).toBeInTheDocument()
})
