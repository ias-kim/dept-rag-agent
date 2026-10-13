"""로그인 시도 제한 — (접속 IP, 아이디)마다 일정 시간 안의 실패 횟수를 센다.

서버가 한 대(EC2 1대)라서 프로세스 메모리로 충분하다. 서버를 여러 대로 늘리면 각자 따로 세므로
그때는 DB나 Redis로 옮겨야 한다. 아이디만 키로 쓰면 남의 계정을 일부러 잠글 수 있어 IP를 함께 쓴다.
"""

import threading
import time
from collections import defaultdict, deque


class LoginThrottle:
    def __init__(self, *, max_failures: int, window_seconds: float, clock=time.monotonic):
        self._max = max_failures
        self._window = window_seconds
        self._clock = clock
        self._failures: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()  # 동기 라우트는 스레드 풀에서 동시에 돈다

    def _recent(self, key: tuple[str, str]) -> deque[float]:
        q = self._failures[key]
        while q and self._clock() - q[0] > self._window:
            q.popleft()
        return q

    def is_blocked(self, key: tuple[str, str]) -> bool:
        with self._lock:
            return len(self._recent(key)) >= self._max

    def record_failure(self, key: tuple[str, str]) -> None:
        with self._lock:
            self._recent(key).append(self._clock())

    def reset(self, key: tuple[str, str]) -> None:
        with self._lock:
            self._failures.pop(key, None)
