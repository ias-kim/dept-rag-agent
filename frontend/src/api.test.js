import { ApiError, NETWORK_ERROR, TOKEN_KEY, ask, getToken, login } from './api'

function json(status, body) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
}

test('login stores token', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockReturnValue(json(200, { access_token: 't1', token_type: 'bearer' }))
  await login('kim', 'pw')
  expect(getToken()).toBe('t1')
  const [url, init] = fetchMock.mock.calls[0]
  expect(url).toBe('/api/auth/login')
  expect(init.method).toBe('POST')
  expect(JSON.parse(init.body)).toEqual({ username: 'kim', password: 'pw' })
})

test('ask sends bearer token and returns body', async () => {
  sessionStorage.setItem(TOKEN_KEY, 't1')
  const body = { answer: 'a', sources: [], intent: null, notices: [] }
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockReturnValue(json(200, body))
  await expect(ask('질문')).resolves.toEqual(body)
  const [url, init] = fetchMock.mock.calls[0]
  expect(url).toBe('/api/ask')
  expect(init.headers.Authorization).toBe('Bearer t1')
  expect(JSON.parse(init.body)).toEqual({ question: '질문' })
})

test('string detail becomes message', async () => {
  sessionStorage.setItem(TOKEN_KEY, 't1')
  vi.spyOn(globalThis, 'fetch').mockReturnValue(json(429, { detail: '오늘 질문 한도를 모두 사용했습니다' }))
  const err = await ask('q').catch((e) => e)
  expect(err).toBeInstanceOf(ApiError)
  expect(err.status).toBe(429)
  expect(err.message).toBe('오늘 질문 한도를 모두 사용했습니다')
})

test('422 list detail becomes generic message', async () => {
  vi.spyOn(globalThis, 'fetch').mockReturnValue(json(422, { detail: [{ loc: ['body', 'question'], msg: 'too long' }] }))
  const err = await ask('q').catch((e) => e)
  expect(err.status).toBe(422)
  expect(err.message).toBe('입력값을 확인해 주세요')
})

test('non-json error body falls back by status', async () => {
  vi.spyOn(globalThis, 'fetch').mockReturnValue(Promise.resolve(new Response('Bad Gateway', { status: 502 })))
  const err = await ask('q').catch((e) => e)
  expect(err.status).toBe(502)
  expect(err.message).toBe(NETWORK_ERROR)
})

test('network failure', async () => {
  vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
  const err = await login('kim', 'pw').catch((e) => e)
  expect(err).toBeInstanceOf(ApiError)
  expect(err.status).toBe(0)
  expect(err.message).toBe(NETWORK_ERROR)
})

test('ask 401 clears token', async () => {
  sessionStorage.setItem(TOKEN_KEY, 't1')
  vi.spyOn(globalThis, 'fetch').mockReturnValue(json(401, { detail: '로그인이 필요합니다' }))
  const err = await ask('q').catch((e) => e)
  expect(err.status).toBe(401)
  expect(getToken()).toBeNull()
})
