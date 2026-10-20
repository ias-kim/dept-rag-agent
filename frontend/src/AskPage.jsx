import { useState } from 'react'
import { ask, clearToken } from './api'
import { noticeLabels } from './notices'

// 원천은 서버 QUESTION_MAX_CHARS (backend/app/api/routes.py). 서버 값만 바꾸면 긴 질문이 422로 거절된다
export const QUESTION_MAX_CHARS = 500

// file은 적재 경로(academic/…/x.pdf). 학생에게는 파일명만, 전체 경로는 title로 남긴다
const fileName = (path) => path.split('/').pop()

function SourceList({ sources }) {
  if (sources.length === 0) return null
  // 본문 [n]은 서버가 sources 순서대로 매긴 번호(answer.py verify_citations) — <ol> 번호와 그대로 맞는다
  return (
    <section>
      <h2>출처</h2>
      <ol className="sources">
        {sources.map((s, i) => (
          <li key={i}>
            <span title={s.file}>{fileName(s.file)}</span>
            {` · p.${s.page}`}
            {s.section ? ` · ${s.section}` : ''}
          </li>
        ))}
      </ol>
    </section>
  )
}

export default function AskPage({ onLogout }) {
  const [question, setQuestion] = useState('')
  const [pending, setPending] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    // 버튼 비활성만 믿지 않는다 — Enter 연타도 막아야 질문마다 깎이는 일일 한도를 지킨다
    if (pending || question.trim() === '') return
    setPending(true)
    setError(null)
    try {
      setResult(await ask(question.trim()))
    } catch (err) {
      if (err.status === 401) {
        onLogout('expired')
        return
      }
      setError(err.message)
    } finally {
      setPending(false)
    }
  }

  function handleLogout() {
    clearToken()
    onLogout()
  }

  const notices = result ? noticeLabels(result.notices) : []

  return (
    <main className="page">
      <header className="topbar">
        <p className="brand">학과 지식 질의응답</p>
        <button type="button" className="secondary" onClick={handleLogout}>로그아웃</button>
      </header>
      <h1>질문하기</h1>
      <p className="hint">학사·공지와 수강 중인 과목의 강의자료에서 찾아 근거와 함께 답합니다.</p>
      <form className="stack" onSubmit={handleSubmit}>
        <label>
          질문
          <textarea value={question} maxLength={QUESTION_MAX_CHARS} onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSubmit(e) }}
            placeholder="예: 2학기 중간고사 기간이 언제야?" />
        </label>
        <div className="row">
          <span className="count">{question.length} / {QUESTION_MAX_CHARS}</span>
          <button type="submit" disabled={pending || question.trim() === ''}>
            {pending ? '답변을 만드는 중…' : '질문하기'}
          </button>
        </div>
      </form>
      {error && <p role="alert" className="error spaced">{error}</p>}
      {result && (
        <article className="answer">
          {notices.length > 0 && (
            <ul role="status" className="notices">
              {notices.map((n) => <li key={n}>{n}</li>)}
            </ul>
          )}
          <p className="answer-text">{result.answer}</p>
          <SourceList sources={result.sources} />
        </article>
      )}
    </main>
  )
}
