"""Serve the ADK web UI behind the demo guard. Used by the Dockerfile.

Locally, `adk web` is still the simplest way to run the agent.
"""
import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from google.adk.cli.fast_api import get_fast_api_app

from web_guard import DemoGuard

load_dotenv()

AGENTS_DIR = str(Path(__file__).resolve().parent)


def _required_env(name: str) -> str:
    value = os.getenv(name, "")
    if not value:
        raise RuntimeError(f"{name} must be set; the public link is never served without a passcode.")
    return value


def build_app() -> DemoGuard:
    adk_app = get_fast_api_app(agents_dir=AGENTS_DIR, web=True, use_local_storage=False)
    return DemoGuard(adk_app, user=_required_env("DEMO_USER"), password=_required_env("DEMO_PASSWORD"))


if __name__ == "__main__":
    uvicorn.run(build_app(), host="0.0.0.0", port=int(os.getenv("PORT", "8080")), proxy_headers=True)
