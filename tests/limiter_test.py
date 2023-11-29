import rate_limiter as rl


def test_rate_limiter():
    endpoint = "/test"
    app = "app"
    r = rl.RateLimiter(
        id_or_name="test_limiter",
        endpoint_name_filter=endpoint,
        app_name_filter=app,
        user_filter=True,
        limit=10,
        window="minute",
        window_buckets=10
    )
    state = rl.ProcessState()
    req = rl.Request(app_id=app, endpoint=endpoint, user_id="1")
    rl.is_limit_reached(state, [r], req)
