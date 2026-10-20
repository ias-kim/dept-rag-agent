import { useEffect, useState } from 'react'
import { ask, clearToken, me } from './api'
import { noticeLabels } from './notices'
import { EXAMPLE_QUESTIONS, QUESTION_MAX_CHARS } from './questions'

// file은 적재 경로(academic/…/x.pdf). 학생에게는 파일명만, 전체 경로는 title로 남긴다
const fileName = (path) => path.split('/').pop()

// 서버가 남기는 [n]은 검증된 인용뿐이다(자료 원문의 [1]은 서버가 전각 ［1］로 바꿔 둔다) — 그래서 반각 [n]만 배지로 바꾼다
const CITATION_RE = /\[(\d+)\]/g

function AnswerText({ text }) {
  const parts = text.split(CITATION_RE) // 홀수 칸이 인용 번호
  return (
    <p className="answer-text">
      {parts.map((part, i) => (i % 2 === 1
        ? <span key={i} className="cite"><span className="sr-only">출처 </span>{part}</span>
        : part))}
    </p>
  )
}

function courseBadge(courses) {
  return courses.length > 0 ? `${courses.join(' · ')} 수강` : '게스트 · 학사 자료만'
}

function SourceList({ sources }) {
  if (sources.length === 0) return null
  // 본문 [n]은 서버가 sources 순서대로 매긴 번호(answer.py verify_citations) — 정렬·중복 제거하면 번호가 어긋난다
  return (
    <section className="sources">
      <h2>이 답변의 근거 자료</h2>
      <ol>
        {sources.map((s, i) => (
          <li key={i} className="source">
            <span className="source-num" aria-hidden="true">{i + 1}</span>
            <span className="pdf" aria-hidden="true">PDF</span>
            <span className="source-text">
              <b title={s.file}>{fileName(s.file)}</b>
              {s.section && <small>{s.section}</small>}
            </span>
            <span className="source-page">{s.page}쪽</span>
          </li>
        ))}
      </ol>
    </section>
  )
}

function AnswerSkeleton() {
  return (
    <div className="card skeleton" role="progressbar" aria-label="답변을 불러오는 중">
      <span /><span /><span className="short" />
    </div>
  )
}

export default function AskPage({ onLogout }) {
  const [profile, setProfile] = useState(null)
  const [question, setQuestion] = useState('')
  const [pending, setPending] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    me().then(
      (p) => { if (active) setProfile(p) },
      // 이미 만료된 토큰이면 질문을 다 쓰기 전에 로그인으로 보낸다. 그 외 실패는 배지만 숨기고 질문은 막지 않는다
      (err) => { if (active && err.status === 401) onLogout('expired') },
    )
    return () => { active = false }
  }, [onLogout])

  async function send() {
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

  function handleKeyDown(e) {
    // 한글 조합 중 Enter는 글자 확정용 — 여기서 보내면 마지막 글자가 빠진 채 전송된다.
    // Safari는 확정 Enter를 isComposing=false, keyCode=229로 보내므로 둘 다 본다
    if (e.key !== 'Enter' || e.shiftKey || e.nativeEvent.isComposing || e.keyCode === 229) return
    e.preventDefault()
    send()
  }

  function handleLogout() {
    clearToken()
    onLogout()
  }

  // 의도가 major면 본문 자체가 수강 안내(pipeline.py MAJOR_ONLY_TEXT)라 띠가 같은 말을 반복한다.
  // both는 학사만 찾은 결과라 출처가 없어도(자료 없음 등) 띠가 있어야 전공 자료가 빠진 것을 안다
  const noticeCodes = result ? result.notices.filter((c) => c !== 'major_requires_enrollment' || result.intent !== 'major') : []
  const notices = noticeLabels(noticeCodes)

  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">🎓 학과 지식 질의응답</span>
        <span className="who">
          {profile && <span className="badge">{courseBadge(profile.courses)}</span>}
          {profile && <span className="username">{profile.username}</span>}
          <button type="button" className="ghost" onClick={handleLogout}>로그아웃</button>
        </span>
      </header>

      <main className="page">
        <h1>무엇이든 물어보세요</h1>
        <p className="lead">학사 공지와 수강 중인 과목의 강의자료에서 찾아, 근거와 함께 답해 드립니다.</p>

        <form className="search" onSubmit={(e) => { e.preventDefault(); send() }}>
          <textarea aria-label="질문" rows={1} value={question} maxLength={QUESTION_MAX_CHARS}
            onChange={(e) => setQuestion(e.target.value)} onKeyDown={handleKeyDown}
            placeholder="궁금한 점을 입력하세요" />
          <button type="submit" disabled={pending || question.trim() === ''}>
            {pending ? '답변을 만드는 중…' : '질문하기'}
          </button>
        </form>
        <div className="meta">
          <span className="examples">
            예시
            {EXAMPLE_QUESTIONS.map((q) => (
              <button key={q} type="button" className="example" onClick={() => setQuestion(q)}>{q}</button>
            ))}
          </span>
          <span className="count">{question.length} / {QUESTION_MAX_CHARS} · Enter 보내기 · Shift+Enter 줄바꿈</span>
        </div>

        {error && <p role="alert" className="error">{error}</p>}
        {pending && <AnswerSkeleton />}
        {!pending && result && (
          <article className="card">
            <p className="label">답변</p>
            {notices.length > 0 && (
              <ul role="status" className="notices">
                {notices.map((n) => <li key={n}>{n}</li>)}
              </ul>
            )}
            <AnswerText text={result.answer} />
            <SourceList sources={result.sources} />
          </article>
        )}
      </main>
    </div>
  )
}
