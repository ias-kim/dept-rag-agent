// 서버와 주고받는 유일한 통로. 계약 원천은 backend/app/api/routes.py (docs/generated/openapi.json).
// 운영은 같은 출처(/api)라 CORS가 없다 — 개발 중에는 vite.config.js 프록시가 :8000으로 넘긴다.

// sessionStorage: 탭을 닫으면 사라진다. localStorage로 바꾸면 공용 PC에서 다음 사람이 로그인된 채로 쓴다
export const TOKEN_KEY = 'dept-rag-token'
export const NETWORK_ERROR = '서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.'
const INVALID_INPUT = '입력값을 확인해 주세요'

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

export const getToken = () => sessionStorage.getItem(TOKEN_KEY)
export const clearToken = () => sessionStorage.removeItem(TOKEN_KEY)

// 서버 detail 문구를 그대로 쓴다: 429는 "로그인 시도 과다"와 "오늘 한도 소진" 두 뜻이라 화면이 추측하면 틀린다
function errorMessage(body) {
  const detail = body?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return INVALID_INPUT // FastAPI 422 검증 오류는 필드 목록
  return NETWORK_ERROR // 프록시 오류 페이지(HTML) 등 서버가 만든 응답이 아닐 때
}

async function request(path, payload, { auth = false } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (auth) headers.Authorization = `Bearer ${getToken()}`
  let res
  try {
    res = await fetch(path, { method: 'POST', headers, body: JSON.stringify(payload) })
  } catch {
    throw new ApiError(0, NETWORK_ERROR)
  }
  const text = await res.text()
  let body = null
  try {
    body = JSON.parse(text)
  } catch {
    // JSON이 아닌 본문 — 아래 errorMessage가 일반 문구로 바꾼다
  }
  if (!res.ok) {
    if (res.status === 401) clearToken() // 만료·삭제된 계정의 토큰을 들고 같은 오류를 반복하지 않게
    throw new ApiError(res.status, errorMessage(body))
  }
  return body
}

export async function login(username, password) {
  const { access_token } = await request('/api/auth/login', { username, password })
  sessionStorage.setItem(TOKEN_KEY, access_token)
}

export function ask(question) {
  return request('/api/ask', { question }, { auth: true })
}
