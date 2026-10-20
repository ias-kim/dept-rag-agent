// 서버와 주고받는 유일한 통로. 계약 원천은 backend/app/api/routes.py (docs/generated/openapi.json).
// 운영은 같은 출처(/api)라 CORS가 없다 — 개발 중에는 vite.config.js 프록시가 :8000으로 넘긴다.

// sessionStorage: 탭을 닫으면 사라진다. localStorage로 바꾸면 공용 PC에서 다음 사람이 로그인된 채로 쓴다
export const TOKEN_KEY = 'dept-rag-token'
export const NETWORK_ERROR = '서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.'
export const SERVER_ERROR = '서버에서 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.'
const INVALID_INPUT = '입력값을 확인해 주세요'
// 502·503·504는 프록시가 앱에 닿지 못한 경우 — "연결할 수 없음"이 맞다. 그 외 5xx는 앱 안의 오류다
const GATEWAY_STATUSES = new Set([502, 503, 504])

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

export const getToken = () => sessionStorage.getItem(TOKEN_KEY)
export const clearToken = () => sessionStorage.removeItem(TOKEN_KEY)

// 서버 detail 문구를 그대로 쓴다: 429는 "로그인 시도 과다"와 "오늘 한도 소진" 두 뜻이라 화면이 추측하면 틀린다
function errorMessage(status, body) {
  const detail = body?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return INVALID_INPUT // FastAPI 422 검증 오류는 필드 목록
  // 본문이 JSON이 아님(프록시 오류 페이지, 처리되지 않은 예외의 500 등)
  return status >= 500 && !GATEWAY_STATUSES.has(status) ? SERVER_ERROR : NETWORK_ERROR
}

async function request(method, path, payload, { auth = false } = {}) {
  const headers = {}
  if (payload !== undefined) headers['Content-Type'] = 'application/json'
  if (auth) headers.Authorization = `Bearer ${getToken()}`
  let res
  try {
    res = await fetch(path, { method, headers, body: payload === undefined ? undefined : JSON.stringify(payload) })
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
    throw new ApiError(res.status, errorMessage(res.status, body))
  }
  return body
}

export async function login(username, password) {
  const { access_token } = await request('POST', '/api/auth/login', { username, password })
  sessionStorage.setItem(TOKEN_KEY, access_token)
}

export function ask(question) {
  return request('POST', '/api/ask', { question }, { auth: true })
}

// 상단 수강 과목 표시용. 한도를 쓰지 않으므로 화면을 열 때마다 불러도 된다
export function me() {
  return request('GET', '/api/me', undefined, { auth: true })
}
