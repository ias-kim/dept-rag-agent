from concurrent.futures import ThreadPoolExecutor

from app.api.throttle import LoginThrottle


def make(now, **kw):
    opts = {"max_per_account": 2, "max_per_ip": 5, "window_seconds": 60, "max_keys": 1000}
    return LoginThrottle(**{**opts, **kw}, clock=lambda: now[0])


def test_block_lifts_after_window():
    # 창이 지나도 계속 막으면, 한 번 실수한 학생이 서버를 다시 켤 때까지 로그인하지 못한다
    now = [0.0]
    t = make(now)
    assert t.try_acquire("1.2.3.4", "kim") and t.try_acquire("1.2.3.4", "kim")
    assert not t.try_acquire("1.2.3.4", "kim")
    now[0] = 61
    assert t.try_acquire("1.2.3.4", "kim")


def test_concurrent_attempts_cannot_exceed_limit():
    # 확인과 기록이 따로면 동시에 들어온 요청이 모두 확인을 통과해 제한을 넘는다
    t = LoginThrottle(max_per_account=5, max_per_ip=100, window_seconds=60, max_keys=1000)
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: t.try_acquire("1.2.3.4", "kim"), range(40)))
    assert results.count(True) == 5


def test_success_clears_account_attempts():
    now = [0.0]
    t = make(now)
    t.try_acquire("1.2.3.4", "kim")
    t.succeeded("1.2.3.4", "kim")
    assert t.try_acquire("1.2.3.4", "kim") and t.try_acquire("1.2.3.4", "kim")


def test_one_ip_cannot_spray_many_usernames():
    # 아이디를 바꿔 가며 시도하면 계정별 제한을 피할 수 있다 — IP별 상한으로 막는다
    now = [0.0]
    t = make(now)
    assert all(t.try_acquire("1.2.3.4", f"user{i}") for i in range(5))
    assert not t.try_acquire("1.2.3.4", "user99")
    assert t.try_acquire("5.6.7.8", "user99")  # 다른 IP는 영향 없음


def test_memory_is_bounded_and_full_table_fails_closed():
    # 임의의 IP·아이디 조합으로 기록을 무한히 늘릴 수 없어야 한다. 꽉 차면 새 조합은 거절(429)한다
    now = [0.0]
    t = make(now, max_keys=10, max_per_ip=10_000)
    results = [t.try_acquire(f"10.0.0.{i}", f"u{i}") for i in range(100)]
    assert results.count(True) == 10 and t.tracked_keys() <= 2 * 10
    now[0] = 61  # 창이 지나면 만료 기록을 치우고 다시 받는다
    assert t.try_acquire("10.0.1.1", "late")


def test_flooding_new_keys_cannot_evict_a_blocked_record():
    # 오래된 기록부터 지우면 공격자가 새 조합을 쏟아부어 자기 차단 기록을 밀어내고 제한을 초기화한다
    now = [0.0]
    t = make(now, max_keys=10, max_per_ip=10_000)
    t.try_acquire("6.6.6.6", "kim")
    t.try_acquire("6.6.6.6", "kim")
    assert not t.try_acquire("6.6.6.6", "kim")
    for i in range(100):
        t.try_acquire(f"7.7.{i}.1", f"x{i}")
    assert not t.try_acquire("6.6.6.6", "kim")
