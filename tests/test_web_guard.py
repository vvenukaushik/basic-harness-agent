import asyncio
import base64

from web_guard import DemoGuard, RateLimiter, client_ip, credentials_match


def basic(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


async def inner_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"agent"})


def call(guard: DemoGuard, path: str, auth: str | None = None, ip: str = "1.2.3.4") -> int:
    headers = [(b"x-forwarded-for", f"9.9.9.9, {ip}".encode())]
    if auth:
        headers.append((b"authorization", auth.encode()))
    scope = {"type": "http", "path": path, "headers": headers, "client": ("10.0.0.1", 1)}
    sent = []

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        sent.append(message)

    asyncio.run(guard(scope, receive, send))
    return sent[0]["status"]


def make_guard(limit: int = 20) -> DemoGuard:
    return DemoGuard(inner_app, user="demo", password="s3cret", limiter=RateLimiter(limit=limit))


def test_missing_or_wrong_passcode_is_401():
    guard = make_guard()
    assert call(guard, "/dev-ui/") == 401
    assert call(guard, "/dev-ui/", basic("demo", "wrong")) == 401
    assert call(guard, "/dev-ui/", "Basic not-base64!!") == 401


def test_correct_passcode_reaches_app():
    assert call(make_guard(), "/dev-ui/", basic("demo", "s3cret")) == 200


def test_health_check_needs_no_passcode():
    assert call(make_guard(), "/healthz") == 200


def test_agent_requests_rate_limited_per_ip():
    guard = make_guard(limit=3)
    auth = basic("demo", "s3cret")
    assert [call(guard, "/run_sse", auth) for _ in range(4)] == [200, 200, 200, 429]
    assert call(guard, "/run_sse", auth, ip="5.6.7.8") == 200


def test_non_agent_paths_not_rate_limited():
    guard = make_guard(limit=1)
    auth = basic("demo", "s3cret")
    assert [call(guard, "/dev-ui/", auth) for _ in range(5)] == [200] * 5


def test_rate_limit_window_slides():
    now = [0.0]
    limiter = RateLimiter(limit=2, clock=lambda: now[0])
    assert limiter.allow("ip") and limiter.allow("ip")
    assert not limiter.allow("ip")
    now[0] = 60.0
    assert limiter.allow("ip")


def test_client_ip_uses_proxy_appended_entry():
    scope = {"headers": [(b"x-forwarded-for", b"spoofed, 7.7.7.7")], "client": ("10.0.0.1", 1)}
    assert client_ip(scope) == "7.7.7.7"
    assert client_ip({"headers": [], "client": ("10.0.0.1", 1)}) == "10.0.0.1"


def test_credentials_match_handles_colon_in_password():
    assert credentials_match(basic("demo", "a:b"), "demo", "a:b")
