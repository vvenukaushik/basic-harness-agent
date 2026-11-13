"""Run scenarios against the live agent and show tool calls.

Usage: python scripts/try_agent.py "conversation one" "turn 1 || turn 2" ...
Each argument is one conversation in a fresh session with fresh store data.
Turns inside a conversation are separated by "||" and share the session.
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from banking_agent import store  # noqa: E402
from banking_agent.agent import root_agent  # noqa: E402

PAUSE_SECONDS = 10  # free tier allows 15 requests/minute; a turn can use 2-3


async def run_conversation(turns: list[str]) -> None:
    store.reset_store()
    runner = InMemoryRunner(agent=root_agent, app_name="banking_agent")
    session = await runner.session_service.create_session(app_name="banking_agent", user_id="demo")
    print("\n" + "=" * 70)
    for i, message in enumerate(turns):
        if i:
            time.sleep(PAUSE_SECONDS)
        print(f"USER: {message}")
        async for event in runner.run_async(
            user_id="demo",
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=message)]),
        ):
            for part in (event.content.parts if event.content else []) or []:
                if part.function_call:
                    print(f"  TOOL CALL   {part.function_call.name}({dict(part.function_call.args or {})})")
                elif part.function_response:
                    print(f"  TOOL RESULT {part.function_response.response}")
                elif part.text and part.text.strip():
                    print(f"AGENT: {part.text.strip()}")
        print(f"  [balance now {store.get_account()['balance']:,}]")


async def main() -> None:
    for i, conversation in enumerate(sys.argv[1:]):
        if i:
            time.sleep(PAUSE_SECONDS)
        await run_conversation([t.strip() for t in conversation.split("||") if t.strip()])


if __name__ == "__main__":
    asyncio.run(main())
