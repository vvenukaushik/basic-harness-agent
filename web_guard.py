"""ASGI middleware that protects the public demo link: passcode and per-IP rate limit.

Pure ASGI (not BaseHTTPMiddleware) so it also covers websocket requests.
"""
import base64
import binascii
import secrets
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

AGENT_PATHS = ("/run", "/run_sse", "/run_live")
HEALTH_PATH = "/healthz"  # unauthenticated so the host's health check can reach it
RATE_LIMIT_PER_MINUTE = 20
WINDOW_SECONDS = 60.0


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1")
    return None


def client_ip(scope: Scope) -> str:
    """Client IP as seen by the host's proxy.

    The rightmost X-Forwarded-For entry is the one the proxy appended,
    so a client cannot spoof it by sending its own header.
    """
    forwarded = _header(scope, b"x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    client = scope.get("client")
    return client[0] if client else "unknown"


def credentials_match(header: str | None, user: str, password: str) -> bool:
    if not header or not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    given_user, _, given_password = decoded.partition(":")
    user_ok = secrets.compare_digest(given_user.encode(), user.encode())
    password_ok = secrets.compare_digest(given_password.encode(), password.encode())
    return user_ok and password_ok


class RateLimiter:
    """Sliding one-minute window per key."""

    def __init__(self, limit: int = RATE_LIMIT_PER_MINUTE, clock: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = self.clock()
        hits = self._hits[key]
        while hits and now - hits[0] >= WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True


async def _respond(scope: Scope, send: Send, status: int, body: bytes, headers: list[tuple[bytes, bytes]]) -> None:
    if scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": 1008})
        return
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", b"text/plain; charset=utf-8"), *headers],
    })
    await send({"type": "http.response.body", "body": body})


class DemoGuard:
    """HTTP Basic Auth on every request, plus a rate limit on agent requests."""

    def __init__(self, app: ASGIApp, user: str, password: str, limiter: RateLimiter | None = None):
        self.app = app
        self.user = user
        self.password = password
        self.limiter = limiter or RateLimiter()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        if scope["type"] == "http" and scope["path"] == HEALTH_PATH:
            await _respond(scope, send, 200, b"ok", [])
            return

        if not credentials_match(_header(scope, b"authorization"), self.user, self.password):
            await _respond(scope, send, 401, b"Passcode required",
                          [(b"www-authenticate", b'Basic realm="banking-demo", charset="UTF-8"')])
            return

        if scope["path"].startswith(AGENT_PATHS) and not self.limiter.allow(client_ip(scope)):
            await _respond(scope, send, 429, b"Too many requests. Try again in a minute.",
                          [(b"retry-after", b"60")])
            return

        await self.app(scope, receive, send)
