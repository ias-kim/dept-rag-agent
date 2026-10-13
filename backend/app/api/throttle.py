"""로그인 시도 제한 — (IP, 아이디)별 + IP별로 일정 시간 안의 시도 횟수를 센다.

- 시도를 **먼저** 기록한다(try_acquire). 확인하고 나중에 실패를 기록하면 동시에 들어온 요청이
  모두 확인을 통과해 제한을 넘는다. 로그인에 성공하면 그 계정 기록만 지운다.
- 아이디만 키로 쓰면 남의 계정을 일부러 잠글 수 있고, IP만 쓰면 같은 강의실 학생이 함께 막힌다.
  그래서 (IP, 아이디)를 좁게, IP를 넓게 함께 센다. IP 상한은 아이디를 바꿔 가며 뿌리는 시도도 막는다.
- 서버가 한 대라 프로세스 메모리에 둔다. 기록 수는 max_keys로 묶는다(만료분부터, 그래도 넘으면 오래된 것부터 지움).
  서버를 여러 대로 늘리면 각자 따로 세므로 그때는 DB나 Redis로 옮긴다.
"""

import threading
import time
from collections import deque


class LoginThrottle:
    def __init__(self, *, max_per_account: int, max_per_ip: int, window_seconds: float, max_keys: int,
                 clock=time.monotonic):
        self._limits = {"account": max_per_account, "ip": max_per_ip}
        self._window = window_seconds
        self._max_keys = max_keys
        self._clock = clock
        self._attempts: dict[str, dict[object, deque[float]]] = {"account": {}, "ip": {}}
        self._lock = threading.Lock()  # 동기 라우트는 스레드 풀에서 동시에 돈다

    def _recent(self, kind: str, key: object, now: float) -> deque[float]:
        q = self._attempts[kind].setdefault(key, deque())
        while q and now - q[0] > self._window:
            q.popleft()
        return q

    def _evict(self, now: float) -> None:
        for table in self._attempts.values():
            if len(table) <= self._max_keys:
                continue
            for key in [k for k, q in table.items() if not q or now - q[-1] > self._window]:
                del table[key]
            if len(table) > self._max_keys:  # 그래도 넘치면 마지막 시도가 가장 오래된 것부터
                for key in sorted(table, key=lambda k: table[k][-1])[: len(table) - self._max_keys]:
                    del table[key]

    def try_acquire(self, ip: str, username: str) -> bool:
        """시도 1회를 기록하고 허용 여부를 돌려준다. 거절된 시도는 기록하지 않는다."""
        with self._lock:
            now = self._clock()
            account = self._recent("account", (ip, username), now)
            per_ip = self._recent("ip", ip, now)
            if len(account) >= self._limits["account"] or len(per_ip) >= self._limits["ip"]:
                return False
            account.append(now)
            per_ip.append(now)
            self._evict(now)
            return True

    def succeeded(self, ip: str, username: str) -> None:
        with self._lock:
            self._attempts["account"].pop((ip, username), None)

    def tracked_keys(self) -> int:
        with self._lock:
            return sum(len(t) for t in self._attempts.values())
