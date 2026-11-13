"""The deployed app behind an HTTPS proxy, as a browser reaches it (no network, no LLM)."""
import pytest
from fastapi.testclient import TestClient

PUBLIC_HOST = "basic-harness-agent.onrender.com"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DEMO_USER", "demo")
    monkeypatch.setenv("DEMO_PASSWORD", "s3cret")
    import main

    app = main.build_app()

    async def behind_proxy(scope, receive, send):
        # The proxy connects over a local socket, so the server address ADK sees is
        # loopback while Host and Origin carry the public name.
        scope["server"] = ("127.0.0.1", 8080)
        await app(scope, receive, send)

    return TestClient(behind_proxy, base_url=f"http://{PUBLIC_HOST}")


def proxied(origin: str) -> dict[str, str]:
    return {"X-Forwarded-Proto": "https", "X-Forwarded-For": "1.2.3.4", "Origin": origin}


def test_browser_on_public_origin_is_allowed(client):
    response = client.get("/list-apps", auth=("demo", "s3cret"), headers=proxied(f"https://{PUBLIC_HOST}"))
    assert response.status_code == 200
    assert response.json() == ["banking_agent"]


def test_foreign_origin_is_still_rejected(client):
    response = client.get("/list-apps", auth=("demo", "s3cret"), headers=proxied("https://evil.example"))
    assert response.status_code == 403


def test_app_refuses_to_start_without_passcode(monkeypatch):
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    monkeypatch.setenv("DEMO_USER", "demo")
    import main

    with pytest.raises(RuntimeError, match="DEMO_PASSWORD"):
        main.build_app()
