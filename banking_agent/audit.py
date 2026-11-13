"""Structured audit log (Stage 4).

Wired in as ADK callbacks so the tools stay clean. Each event is one JSON line
on stdout (Cloud Run captures it) and, locally, in logs/audit.jsonl.
Events for the current process are also kept in memory per session so the
get_audit_log tool can show them in the chat.

Full account numbers are never logged: every value passes through redact().
"""
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from .store import mask

AUDIT_FILE_ENV = "AUDIT_LOG_FILE"            # set to "" to disable the file (e.g. on Cloud Run)
DEFAULT_AUDIT_FILE = "logs/audit.jsonl"
MAX_EVENTS_PER_SESSION = 500

_ACCOUNT_NUMBER = re.compile(r"\d{12,}")      # anything that looks like an account number

# Tools whose results are policy decisions.
DECISION_TOOLS = {"initiate_transfer", "confirm_transfer"}


class AuditEvent(str, Enum):
    USER_MESSAGE = "USER_MESSAGE"
    TOOL_CALL = "TOOL_CALL"
    TOOL_RESULT = "TOOL_RESULT"
    POLICY_DECISION = "POLICY_DECISION"
    TRANSFER_EXECUTED = "TRANSFER_EXECUTED"


_events: dict[str, list[dict]] = defaultdict(list)
_logged_invocations: set[tuple[str, str]] = set()  # (session_id, invocation_id)


def redact(value: Any) -> Any:
    """Mask anything that looks like a full account number, recursively."""
    if isinstance(value, str):
        return _ACCOUNT_NUMBER.sub(lambda m: mask(m.group()), value)
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


def log_event(
    event: AuditEvent,
    session_id: str,
    invocation_id: str,
    tool: str | None = None,
    args: dict | None = None,
    status: str | None = None,
    reason: str | None = None,
    **extra: Any,
) -> dict:
    payload = redact({"tool": tool, "args": args, "status": status, "reason": reason, **extra})
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "session_id": session_id,
        "invocation_id": invocation_id,
        "event": event.value,
        **{k: v for k, v in payload.items() if v is not None},
    }
    line = json.dumps(record, default=str)
    print(line, file=sys.stdout, flush=True)
    path = os.getenv(AUDIT_FILE_ENV, DEFAULT_AUDIT_FILE)
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    session_events = _events[session_id]
    session_events.append(record)
    del session_events[:-MAX_EVENTS_PER_SESSION]
    return record


def session_events(session_id: str) -> list[dict]:
    return list(_events.get(session_id, []))


def clear() -> None:
    """For tests."""
    _events.clear()
    _logged_invocations.clear()


# --- ADK callbacks ----------------------------------------------------------

def before_model_callback(callback_context, llm_request):
    """Log the user's message once per invocation (the model may be called several times)."""
    sid, inv = callback_context.session.id, callback_context.invocation_id
    if (sid, inv) in _logged_invocations:
        return None
    _logged_invocations.add((sid, inv))
    content = callback_context.user_content
    text = " ".join(p.text for p in (content.parts or []) if getattr(p, "text", None)) if content else ""
    log_event(AuditEvent.USER_MESSAGE, sid, inv, message=text)
    return None


def before_tool_callback(tool, args, tool_context):
    log_event(AuditEvent.TOOL_CALL, tool_context.session.id, tool_context.invocation_id, tool=tool.name, args=dict(args))
    return None


def after_tool_callback(tool, args, tool_context, tool_response):
    sid, inv = tool_context.session.id, tool_context.invocation_id
    response = tool_response if isinstance(tool_response, dict) else {"value": tool_response}
    status, reason = response.get("status"), response.get("reason")

    if tool.name != "get_audit_log":  # don't log the log into itself
        log_event(AuditEvent.TOOL_RESULT, sid, inv, tool=tool.name, status=status, reason=reason, result=response)

    if tool.name in DECISION_TOOLS:
        log_event(
            AuditEvent.POLICY_DECISION, sid, inv, tool=tool.name, status=status, reason=reason,
            message=response.get("message"), pending_id=response.get("pending_id") or args.get("pending_id"),
        )
    if tool.name == "confirm_transfer" and status == "COMPLETED":
        log_event(
            AuditEvent.TRANSFER_EXECUTED, sid, inv, tool=tool.name, status=status,
            transfer_id=response.get("transfer_id"), amount=response.get("amount"),
            beneficiary=response.get("beneficiary"), pending_id=args.get("pending_id"),
        )
    return None
