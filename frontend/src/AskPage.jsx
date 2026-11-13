import { Fragment, useEffect, useRef, useState } from 'react'
import { ask, clearToken, courseDocuments, me } from './api'
import { noticeLabels } from './notices'
import { EXAMPLE_QUESTIONS, HISTORY_ANSWER_MAX_CHARS, HISTORY_MAX_TURNS, QUESTION_MAX_CHARS } from './questions'

// file은 적재 경로(academic/…/x.pdf). 학생에게는 파일명만, 전체 경로는 title로 남긴다
const fileName = (path) => path.split('/').pop()

// 서버가 남기는 [n]은 검증된 인용뿐이다(자료 원문의 [1]은 서버가 전각 ［1］로 바꿔 둔다) — 그래서 반각 [n]만 배지로 바꾼다
const CITATION_RE = /\[(\d+)\]/g
// 모델이 쓰는 **굵게**만 <strong>으로 바꾼다. 답변은 자료 원문을 옮긴 모델 출력이라 HTML로 넣지 않는다(XSS).
// 양쪽 ** 가 글자에 붙고 영문·숫자 사이에 끼지 않을 때만 강조로 본다. 짝만 보면 **kwargs·2**3의 ** 가 사라져
// 코드와 수식이 다른 내용으로 읽힌다. \w는 ASCII만 잡으므로 **굵게**입니다 처럼 한글에 붙은 강조는 그대로 굵게 된다
const BOLD_RE = /(?<![\w*])\*\*(?=\S)(.+?)(?<=\S)\*\*(?![\w*])/g

function withCitations(text, keyPrefix) {
  return text.split(CITATION_RE).map((part, i) => (i % 2 === 1 // 홀수 칸이 인용 번호
    ? <span key={`${keyPrefix}-${i}`} className="cite"><span className="sr-only">출처 </span>{part}</span>
    : part))
}

function AnswerText({ text }) {
  const parts = text.split(BOLD_RE) // 홀수 칸이 굵은 글씨 — 그 안의 [n]도 배지로 바꾼다
  return (
    <p className="answer-text">
      {parts.map((part, i) => (i % 2 === 1
        ? <strong key={i}>{withCitations(part, i)}</strong>
        : <Fragment key={i}>{withCitations(part, i)}</Fragment>))}
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

// 사이드바는 1~3학년을 항상 보여 준다 — 수강 과목이 없는 학년도 칸이 있어야 "이 학년 과목은 안 듣는다"가 보인다.
// 카탈로그에 학년이 없는 과목은 "기타"로 맨 뒤에
const GRADES = [1, 2, 3]

function groupByGrade(details) {
  const groups = GRADES.map((g) => ({ label: `${g}학년`, courses: details.filter((c) => c.grade === g) }))
  const others = details.filter((c) => !GRADES.includes(c.grade))
  if (others.length > 0) groups.push({ label: '기타', courses: others })
  return groups
}

function courseMeta(c) {
  const term = c.semesters.length > 0 ? `${c.semesters.join(' · ')}학기` : ''
  return [c.name !== c.code ? c.code : '', term].filter(Boolean).join(' · ')
}

// locked: 답을 기다리는 중에는 과목을 못 바꾼다 — 바꾸면 늦게 온 이전 과목 답이 새 대화에 붙어 다음 이력으로 나간다
function Sidebar({ profile, selected, onSelect, locked }) {
  const details = profile?.course_details ?? []
  return (
    <aside className="sidebar" aria-label="과목 선택">
      <p className="sidebar-title">내 과목</p>
      {profile && details.length === 0 && (
        <p className="hint">수강 중인 전공 과목이 없어 학사 공지만 검색합니다.</p>
      )}
      {details.length > 0 && (
        <nav aria-label="내 과목">
          <button type="button" className="course-item all" aria-pressed={selected === null} disabled={locked}
            onClick={() => onSelect(null)}>
            <span className="course-name">전체 과목</span>
            <span className="course-meta">수강 과목 전체 + 학사 공지</span>
          </button>
          {groupByGrade(details).map((g) => {
            const id = `grade-${g.label}`
            return (
              <section key={g.label} className="grade" aria-labelledby={id}>
                <div className="grade-head">
                  <h2 id={id}>{g.label}</h2>
                  {g.courses.length > 0 && <span className="grade-count" aria-hidden="true">{g.courses.length}</span>}
                </div>
                {g.courses.length === 0 && <p className="grade-empty">수강 과목 없음</p>}
                {g.courses.map((c) => (
                  <button key={c.code} type="button" className="course-item" aria-pressed={selected?.code === c.code}
                    disabled={locked} onClick={() => onSelect(c)}>
                    <span className="course-name">{c.name}</span>
                    {courseMeta(c) && <span className="course-meta">{courseMeta(c)}</span>}
                  </button>
                ))}
              </section>
            )
          })}
        </nav>
      )}
    </aside>
  )
}

function MaterialsPanel({ course, materials }) {
  const title = `${course.name} 강의자료`
  return (
    <section className="materials" aria-label={title}>
      <h2>{title}{materials.items && <small>{materials.items.length}개</small>}</h2>
      <p className="hint">이 과목 강의자료와 학사 공지에서만 찾아 답합니다.</p>
      {materials.error && <p className="hint">강의자료 목록을 불러오지 못했습니다. 질문은 그대로 할 수 있습니다.</p>}
      {materials.items && materials.items.length === 0 && <p className="hint">아직 올라온 강의자료가 없습니다.</p>}
      {materials.items && materials.items.length > 0 && (
        <ul>
          {materials.items.map((d) => (
            <li key={d.file}>
              <span className="pdf" aria-hidden="true">PDF</span>
              <span className="material-name" title={d.file}>{d.file}</span>
              <span className="source-page">{d.pages}쪽</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

// 서버로 보낼 앞 대화. 상한을 넘기면 질문 전체가 422가 되므로 서버와 같은 값으로 자른다
function toHistory(turns) {
  return turns.slice(-HISTORY_MAX_TURNS).map((t) => ({
    question: t.question, answer: t.result.answer.slice(0, HISTORY_ANSWER_MAX_CHARS),
  }))
}

// 의도가 major면 본문 자체가 수강 안내(pipeline.py MAJOR_ONLY_TEXT)라 띠가 같은 말을 반복한다.
// both는 학사만 찾은 결과라 출처가 없어도(자료 없음 등) 띠가 있어야 전공 자료가 빠진 것을 안다
function visibleNotices(result) {
  return noticeLabels(result.notices.filter((c) => c !== 'major_requires_enrollment' || result.intent !== 'major'))
}

function TurnCard({ turn }) {
  const notices = visibleNotices(turn.result)
  return (
    <article className="card turn">
      <p className="asked"><span className="sr-only">질문 </span>{turn.question}</p>
      <p className="label">답변{turn.course && <span className="scope"> · {turn.course.name}</span>}</p>
      {notices.length > 0 && (
        <ul role="status" className="notices">
          {notices.map((n) => <li key={n}>{n}</li>)}
        </ul>
      )}
      <AnswerText text={turn.result.answer} />
      <SourceList sources={turn.result.sources} />
    </article>
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
  const [turns, setTurns] = useState([]) // 이 탭의 대화. 새로고침하면 사라진다(서버에 저장하지 않음)
  const [error, setError] = useState(null)
  const [course, setCourse] = useState(null) // null = 수강 과목 전체
  const [materials, setMaterials] = useState({})
  const endRef = useRef(null)

  useEffect(() => {
    let active = true
    me().then(
      (p) => { if (active) setProfile(p) },
      // 이미 만료된 토큰이면 질문을 다 쓰기 전에 로그인으로 보낸다. 그 외 실패는 배지만 숨기고 질문은 막지 않는다
      (err) => { if (active && err.status === 401) onLogout('expired') },
    )
    return () => { active = false }
  }, [onLogout])

  useEffect(() => {
    if (!course) return undefined
    let active = true
    courseDocuments(course.code).then(
      (items) => { if (active) setMaterials({ items }) },
      (err) => {
        if (!active) return
        if (err.status === 401) onLogout('expired')
        else setMaterials({ error: true })
      },
    )
    return () => { active = false } // 과목을 빠르게 바꾸면 늦게 온 이전 과목 목록이 덮어쓰지 않게
  }, [course, onLogout])

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' })
  }, [turns.length, pending])

  function selectCourse(next) {
    if ((next?.code ?? null) === (course?.code ?? null)) return
    // 과목이 바뀌면 대화를 새로 시작한다 — 앞 과목 대화가 남으면 후속 질문 재작성이 이전 과목 주제로 끌려간다
    setCourse(next)
    setMaterials({}) // 새 과목 목록이 올 때까지 이전 과목 목록을 보이지 않는다
    setTurns([])
    setError(null)
  }

  function newConversation() {
    setTurns([])
    setError(null)
  }

  async function send() {
    // 버튼 비활성만 믿지 않는다 — Enter 연타도 막아야 질문마다 깎이는 일일 한도를 지킨다
    if (pending || question.trim() === '') return
    const asked = question.trim()
    setPending(true)
    setError(null)
    try {
      const result = await ask(asked, { course: course?.code ?? null, history: toHistory(turns) })
      // 실패한 질문은 대화에 넣지 않는다 — 답 없는 턴이 이력으로 가면 재작성 모델이 빈 답을 맥락으로 쓴다
      setTurns((prev) => [...prev, { question: asked, result, course }])
      // 보낸 그대로일 때만 비운다 — 기다리는 동안 이어 쓴 글을 답 도착과 함께 지우지 않게
      setQuestion((current) => (current.trim() === asked ? '' : current))
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

  const placeholder = turns.length > 0 ? '이어서 물어보세요 (예: 그럼 그건 언제 써?)'
    : course ? `${course.name}에 대해 궁금한 점을 입력하세요` : '궁금한 점을 입력하세요'

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

      <div className="layout">
      <Sidebar profile={profile} selected={course} onSelect={selectCourse} locked={pending} />
      <main className="page">
        <h1>무엇이든 물어보세요</h1>
        <p className="lead">학사 공지와 수강 중인 과목의 강의자료에서 찾아, 근거와 함께 답해 드립니다.</p>

        {course && <MaterialsPanel course={course} materials={materials} />}

        {turns.length > 0 && (
          <div className="thread-head">
            <span>대화 {turns.length}개 · 앞 대화를 이어서 이해합니다</span>
            <button type="button" className="ghost" onClick={newConversation} disabled={pending}>새 대화</button>
          </div>
        )}
        <div className="thread">
          {turns.map((t, i) => <TurnCard key={i} turn={t} />)}
          {pending && <AnswerSkeleton />}
        </div>
        {error && <p role="alert" className="error">{error}</p>}

        <form className="search" onSubmit={(e) => { e.preventDefault(); send() }}>
          <textarea aria-label="질문" rows={1} value={question} maxLength={QUESTION_MAX_CHARS}
            onChange={(e) => setQuestion(e.target.value)} onKeyDown={handleKeyDown}
            placeholder={placeholder} />
          <button type="submit" disabled={pending || question.trim() === ''}>
            {pending ? '답변을 만드는 중…' : '질문하기'}
          </button>
        </form>
        <div className="meta" ref={endRef}>
          {turns.length === 0 && (
            <span className="examples">
              예시
              {EXAMPLE_QUESTIONS.map((q) => (
                <button key={q} type="button" className="example" onClick={() => setQuestion(q)}>{q}</button>
              ))}
            </span>
          )}
          <span className="count">{question.length} / {QUESTION_MAX_CHARS} · Enter 보내기 · Shift+Enter 줄바꿈</span>
        </div>
      </main>
      </div>
    </div>
  )
}
