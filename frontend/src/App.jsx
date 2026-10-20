import { useState } from 'react'
import AskPage from './AskPage'
import { getToken } from './api'
import LoginPage from './LoginPage'
import './App.css'

const EXPIRED_NOTICE = '로그인이 만료되었습니다. 다시 로그인해 주세요.'

// 라우터 라이브러리 없이 토큰 유무로만 화면을 고른다 — 화면이 둘뿐이라 주소 관리가 필요 없다
export default function App() {
  const [loggedIn, setLoggedIn] = useState(() => getToken() !== null)
  const [notice, setNotice] = useState()

  if (!loggedIn) {
    return <LoginPage notice={notice} onLoggedIn={() => { setNotice(undefined); setLoggedIn(true) }} />
  }
  return (
    <AskPage onLogout={(reason) => { setNotice(reason === 'expired' ? EXPIRED_NOTICE : undefined); setLoggedIn(false) }} />
  )
}
