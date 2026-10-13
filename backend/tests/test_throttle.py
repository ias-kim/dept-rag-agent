from app.api.throttle import LoginThrottle

KEY = ("1.2.3.4", "kim")


def test_block_lifts_after_window():
    # 창이 지나도 계속 막으면, 한 번 실수한 학생이 서버를 다시 켤 때까지 로그인하지 못한다
    now = [0.0]
    t = LoginThrottle(max_failures=2, window_seconds=60, clock=lambda: now[0])
    t.record_failure(KEY)
    t.record_failure(KEY)
    assert t.is_blocked(KEY)
    now[0] = 61
    assert not t.is_blocked(KEY)


def test_keys_are_independent():
    t = LoginThrottle(max_failures=1, window_seconds=60)
    t.record_failure(KEY)
    assert t.is_blocked(KEY) and not t.is_blocked(("5.6.7.8", "kim")) and not t.is_blocked(("1.2.3.4", "lee"))
