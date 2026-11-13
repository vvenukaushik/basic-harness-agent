"""Audit log: callbacks driven directly with fake ADK objects (no runner, no LLM)."""
import json

from google.genai import types

from banking_agent import audit, mock_data, tools
from tests.test_transfer_flow import FakeToolContext

TOOLS = {
    "initiate_transfer": lambda ctx, a: tools.initiate_transfer(tool_context=ctx, **a),
    "confirm_transfer": lambda ctx, a: tools.confirm_transfer(tool_context=ctx, **a),
    "find_beneficiaries": lambda ctx, a: tools.find_beneficiaries(**a),
    "get_audit_log": lambda ctx, a: tools.get_audit_log(tool_context=ctx),
}


class FakeTool:
    def __init__(self, name):
        self.name = name


class FakeCallbackContext:
    def __init__(self, ctx: FakeToolContext, text: str):
        self.invocation_id = ctx.invocation_id
        self.session = ctx.session
        self.user_content = types.Content(role="user", parts=[types.Part(text=text)])


def user_says(ctx, text):
    """What ADK does at the start of a turn (the model may be called more than once)."""
    ctx.next_turn()
    audit.before_model_callback(FakeCallbackContext(ctx, text), llm_request=None)
    audit.before_model_callback(FakeCallbackContext(ctx, text), llm_request=None)


def call_tool(ctx, name, **args):
    """What ADK does around a tool call."""
    tool = FakeTool(name)
    audit.before_tool_callback(tool, args, ctx)
    response = TOOLS[name](ctx, args)
    audit.after_tool_callback(tool, args, ctx, response)
    return response


def test_full_chain_for_one_transfer_in_order(isolated_audit_log):
    ctx = FakeToolContext()
    user_says(ctx, "Transfer 10,000 to John Smith")
    pid = call_tool(ctx, "initiate_transfer", amount=10_000, beneficiary_name="John Smith")["pending_id"]
    user_says(ctx, "yes")
    call_tool(ctx, "confirm_transfer", pending_id=pid)

    events = audit.session_events(ctx.session.id)
    assert [(e["event"], e.get("tool"), e.get("status")) for e in events] == [
        ("USER_MESSAGE", None, None),
        ("TOOL_CALL", "initiate_transfer", None),
        ("TOOL_RESULT", "initiate_transfer", "PENDING_CONFIRMATION"),
        ("POLICY_DECISION", "initiate_transfer", "PENDING_CONFIRMATION"),
        ("USER_MESSAGE", None, None),
        ("TOOL_CALL", "confirm_transfer", None),
        ("TOOL_RESULT", "confirm_transfer", "COMPLETED"),
        ("POLICY_DECISION", "confirm_transfer", "COMPLETED"),
        ("TRANSFER_EXECUTED", "confirm_transfer", "COMPLETED"),
    ]
    assert events[0]["message"] == "Transfer 10,000 to John Smith"
    assert events[-1]["pending_id"] == pid and events[-1]["transfer_id"].startswith("TXN-")
    assert all(e["session_id"] == ctx.session.id for e in events)

    lines = [json.loads(line) for line in isolated_audit_log.read_text().splitlines()]
    assert lines == events


def test_rejection_reason_is_logged():
    ctx = FakeToolContext()
    user_says(ctx, "Send 25,000 to Nick")
    call_tool(ctx, "initiate_transfer", amount=25_000, beneficiary_name="Nick")
    decision = [e for e in audit.session_events(ctx.session.id) if e["event"] == "POLICY_DECISION"][0]
    assert (decision["status"], decision["reason"]) == ("REJECTED", "BENEFICIARY_BLOCKED")


def test_no_full_account_numbers_in_log(isolated_audit_log):
    ctx = FakeToolContext()
    full = [mock_data.ACCOUNT["account_number"]] + [b["account_number"] for b in mock_data.BENEFICIARIES]
    user_says(ctx, f"Send 100 to account {full[1]}")       # user types a full number
    call_tool(ctx, "find_beneficiaries", name_query="john")
    call_tool(ctx, "initiate_transfer", amount=100, beneficiary_name="John")
    text = isolated_audit_log.read_text() + repr(audit.session_events(ctx.session.id))
    assert not any(n in text for n in full)
    assert "****4411" in text


def test_get_audit_log_returns_only_this_session():
    a, b = FakeToolContext(), FakeToolContext()
    user_says(a, "hello from a")
    user_says(b, "hello from b")
    result = call_tool(a, "get_audit_log")
    assert result["status"] == "OK"
    assert [e["message"] for e in result["events"] if e["event"] == "USER_MESSAGE"] == ["hello from a"]
    assert all(e["session_id"] == a.session.id for e in result["events"])
    # Reading the log is itself not logged as a TOOL_RESULT (no log-in-log growth).
    assert not any(e["event"] == "TOOL_RESULT" for e in audit.session_events(a.session.id))


def test_redact_masks_long_digit_runs_only():
    assert audit.redact("acct 7788001122334411, amount 75000") == "acct ****4411, amount 75000"
