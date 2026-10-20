import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// 테스트끼리 토큰·모의 함수가 새면 "로그인된 상태"가 다음 테스트로 넘어가 결과가 순서에 따라 바뀐다
afterEach(() => {
  cleanup()
  sessionStorage.clear()
  vi.clearAllMocks() // vi.mock 모듈의 호출 기록 — restoreAllMocks는 spyOn만 되돌린다
  vi.restoreAllMocks()
})
