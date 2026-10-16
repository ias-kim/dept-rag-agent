"""로그인 시도 제한 — (IP, 아이디)별 + IP별로 일정 시간 안의 시도 횟수를 센다.

- 시도를 **먼저** 기록한다(try_acquire). 확인하고 나중에 실패를 기록하면 동시에 들어온 요청이
  모두 확인을 통과해 제한을 넘는다. 로그인에 성공하면 그 계정 기록만 지운다.
- 아이디만 키로 쓰면 남의 계정을 일부러 잠글 수 있고, IP만 쓰면 같은 강의실 학생이 함께 막힌다.
  그래서 (IP, 아이디)를 좁게, IP를 넓게 함께 센다. IP 상한은 아이디를 바꿔 가며 뿌리는 시도도 막는다.
- 서버가 한 대라 프로세스 메모리에 둔다. 기록 수는 max_keys로 묶되 **창 안의 기록은 절대 지우지 않는다**.
  오래된 것부터 지우면 공격자가 새 조합을 쏟아부어 자기 차단 기록을 밀어내고 제한을 초기화한다.
  유효한 기록만으로 꽉 차면 새 조합을 거절한다(안전 쪽 실패 — 대량 IP 공격 동안 정상 사용자도 잠시 429).
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

    def _recent(self, kind: str, key: object, now: float) -> deque[float] | None:
        """창 안의 시도 목록. 없는 키는 None — 새 키를 만들지는 여기서 정하지 않는다."""
        q = self._attempts[kind].get(key)
        if q is None:
            return None
        while q and now - q[0] > self._window:
            q.popleft()
        return q

    def _has_room(self, kind: str, now: float) -> bool:
        table = self._attempts[kind]
        if len(table) < self._max_keys:
            return True
        for key in [k for k, q in table.items() if not q or now - q[-1] > self._window]:
            del table[key]  # 만료된 기록만 치운다
        return len(table) < self._max_keys

    def try_acquire(self, ip: str, username: str) -> bool:
        """시도 1회를 기록하고 허용 여부를 돌려준다. 거절된 시도는 기록하지 않는다."""
        with self._lock:
            now = self._clock()
            account = self._recent("account", (ip, username), now)
            per_ip = self._recent("ip", ip, now)
            if account is not None and len(account) >= self._limits["account"]:
                return False
            if per_ip is not None and len(per_ip) >= self._limits["ip"]:
                return False
            if (account is None and not self._has_room("account", now)) or (per_ip is None and not self._has_room("ip", now)):
                return False  # 유효한 기록으로 꽉 참 — 지우지 않고 새 조합을 거절
            self._attempts["account"].setdefault((ip, username), deque()).append(now)
            self._attempts["ip"].setdefault(ip, deque()).append(now)
            return True

    def succeeded(self, ip: str, username: str) -> None:
        with self._lock:
            self._attempts["account"].pop((ip, username), None)

    def tracked_keys(self) -> int:
        with self._lock:
            return sum(len(t) for t in self._attempts.values())
