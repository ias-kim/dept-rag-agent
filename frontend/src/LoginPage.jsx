import { useState } from 'react'
import { login } from './api'

export default function LoginPage({ onLoggedIn, notice }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    if (pending) return
    setPending(true)
    setError(null)
    try {
      await login(username, password)
      onLoggedIn()
    } catch (err) {
      setError(err.message)
      setPending(false)
    }
  }

  const canSubmit = username.trim() !== '' && password !== '' && !pending

  return (
    <main className="login">
      <div className="login-card">
        <span className="brand">🎓 학과 지식 질의응답</span>
        <h1>로그인</h1>
        <p className="lead">학사 공지와 강의자료를 근거와 함께 찾아 드립니다. 계정은 튜터에게 받습니다.</p>
        {notice && <p className="notice">{notice}</p>}
        <form className="stack" onSubmit={handleSubmit}>
          <label>
            아이디
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          </label>
          <label>
            비밀번호
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password" />
          </label>
          {error && <p role="alert" className="error">{error}</p>}
          <button type="submit" disabled={!canSubmit}>{pending ? '확인 중…' : '로그인'}</button>
        </form>
      </div>
    </main>
  )
}
