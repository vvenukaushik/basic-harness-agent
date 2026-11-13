"""Tool functions exposed to the agent.

Tools fetch data, call the policy, mask results and act on the decision.
They never re-implement rules. Every response is a dict with a `status`.

Stage 3: money moves only through initiate_transfer -> confirm_transfer,
with the pending transfer held in this session's state.
"""
import secrets
import time

from google.adk.tools import ToolContext

from . import audit, store
from .models import PolicyDecision, Reason, TransferStatus
from .policy import PolicyService, check_confirmation, match_beneficiaries

PENDING_KEY = "pending_transfers"
COMPLETED_KEY = "completed_transfers"
AUDIT_LOG_MAX_EVENTS = 50


def _now() -> float:
    """Clock seam so tests can move time."""
    return time.time()


def check_balance() -> dict:
    """Get the customer's current account balance, daily transfer limit and amount transferred today (USD)."""
    a = store.get_account()
    return {
        "status": "OK",
        "account": store.mask(a["account_number"]),
        "balance": a["balance"],
        "daily_limit": a["daily_limit"],
        "transferred_today": a["transferred_today"],
    }


def find_beneficiaries(name_query: str) -> dict:
    """Search the customer's saved beneficiaries by name.

    Args:
        name_query: Beneficiary name, full or first/last name.
    """
    matches = match_beneficiaries(name_query, store.get_beneficiaries())
    if not matches:
        return {"status": "NOT_FOUND", "message": f"No beneficiary matches '{name_query}'."}
    return {"status": "OK", "beneficiaries": [store.public_beneficiary(b) for b in matches]}


def initiate_transfer(
    amount: int, tool_context: ToolContext, beneficiary_name: str = "", beneficiary_id: str = ""
) -> dict:
    """Start a transfer to a saved beneficiary. Does not move money.

    Identify the beneficiary by name, or by beneficiary_id (e.g. BEN-01) when known.

    Statuses: PENDING_CONFIRMATION (returns a `pending_id` and a `summary`; use
    confirm_transfer or cancel_transfer with that id), NEEDS_CLARIFICATION
    (more than one beneficiary matched; `candidates` lists them), REJECTED
    (`reason` and `message` explain why).

    Args:
        amount: Amount in whole USD.
        beneficiary_name: Name of the beneficiary.
        beneficiary_id: Beneficiary ID such as BEN-01.
    """
    amount = _whole(amount)
    decision = _validate(amount, beneficiary_name or None, beneficiary_id or None, _completed(tool_context))
    if decision.status != TransferStatus.APPROVED:
        return decision_to_response(decision)

    beneficiary = decision.beneficiary
    pending_id = f"PND-{secrets.token_hex(3).upper()}"
    pending = dict(tool_context.state.get(PENDING_KEY) or {})
    pending[pending_id] = {
        "amount": amount,
        "beneficiary_id": beneficiary["beneficiary_id"],
        "created_at": _now(),
        "invocation_id": tool_context.invocation_id,
    }
    tool_context.state[PENDING_KEY] = pending
    return {
        "status": TransferStatus.PENDING_CONFIRMATION.value,
        "pending_id": pending_id,
        "summary": {"to": store.public_beneficiary(beneficiary), "amount": amount},
        "message": "Nothing has moved yet. Show the user this summary and ask them to confirm or cancel.",
    }


def confirm_transfer(pending_id: str, tool_context: ToolContext) -> dict:
    """Execute a pending transfer that the user has confirmed.

    Statuses: COMPLETED (money moved; returns `transfer_id` and `new_balance`),
    REJECTED (nothing moved; `reason` and `message` explain why).

    Args:
        pending_id: The pending_id returned by initiate_transfer (e.g. PND-1A2B3C).
    """
    pending_id = _norm_id(pending_id)
    entry = (tool_context.state.get(PENDING_KEY) or {}).get(pending_id)

    rejection = check_confirmation(entry, pending_id, _now(), tool_context.invocation_id)
    if rejection is not None:
        if rejection.reason == Reason.PENDING_EXPIRED:
            _drop(tool_context, pending_id)
        return decision_to_response(rejection)

    # Single use: consume the entry before executing.
    _drop(tool_context, pending_id)

    # Re-validate: balances, limits and the session count may have changed since initiation.
    decision = _validate(entry["amount"], None, entry["beneficiary_id"], _completed(tool_context))
    if decision.status != TransferStatus.APPROVED:
        return decision_to_response(decision)

    transfer = store.record_transfer(entry["beneficiary_id"], entry["amount"])
    tool_context.state[COMPLETED_KEY] = _completed(tool_context) + 1
    return {
        "status": TransferStatus.COMPLETED.value,
        "transfer_id": transfer["transfer_id"],
        "beneficiary": store.public_beneficiary(decision.beneficiary),
        "amount": entry["amount"],
        "new_balance": store.get_account()["balance"],
    }


def cancel_transfer(pending_id: str, tool_context: ToolContext) -> dict:
    """Cancel a pending transfer. No money moves.

    Statuses: CANCELLED, or REJECTED with reason PENDING_NOT_FOUND.

    Args:
        pending_id: The pending_id returned by initiate_transfer.
    """
    pending_id = _norm_id(pending_id)
    if pending_id not in (tool_context.state.get(PENDING_KEY) or {}):
        return decision_to_response(check_confirmation(None, pending_id, _now(), tool_context.invocation_id))
    _drop(tool_context, pending_id)
    return {
        "status": TransferStatus.CANCELLED.value,
        "pending_id": pending_id,
        "message": "Transfer cancelled. Nothing moved.",
    }


def get_transfer_status(transfer_id: str) -> dict:
    """Look up a past transfer by its transfer ID (e.g. TXN-1A2B3C).

    Args:
        transfer_id: The transfer ID returned when the transfer was made.
    """
    t = store.find_transfer(transfer_id)
    if t is None:
        return {"status": "NOT_FOUND", "message": f"No transfer with ID '{transfer_id}'."}
    return {"status": "OK", "transfer": dict(t)}


def get_audit_log(tool_context: ToolContext) -> dict:
    """Get the audit trail of this chat session: user messages, tool calls, policy decisions and executed transfers, oldest first.

    Useful when the user asks why something happened.
    """
    events = audit.session_events(tool_context.session.id)
    return {"status": "OK", "count": len(events), "events": events[-AUDIT_LOG_MAX_EVENTS:]}


def reset_demo_data() -> dict:
    """Reset the demo account, beneficiaries and transfers back to their starting values."""
    store.reset_store()
    return {"status": "OK", "message": "Demo data reset.", "balance": store.get_account()["balance"]}


# --- helpers ---------------------------------------------------------------

def decision_to_response(decision: PolicyDecision) -> dict:
    """Turn a policy decision into a masked tool response."""
    response = {"status": decision.status.value, "message": decision.message}
    if decision.reason:
        response["reason"] = decision.reason.value
    if decision.candidates:
        response["candidates"] = [
            {k: v for k, v in store.public_beneficiary(b).items() if k != "status"} for b in decision.candidates
        ]
    return response


def _validate(amount, beneficiary_name, beneficiary_id, completed_transfers: int) -> PolicyDecision:
    return PolicyService.validate_transfer(
        account=store.get_account(),
        beneficiaries=store.get_beneficiaries(),
        amount=amount,
        beneficiary_name=beneficiary_name,
        beneficiary_id=beneficiary_id,
        completed_transfers=completed_transfers,
    )


def _completed(tool_context: ToolContext) -> int:
    return int(tool_context.state.get(COMPLETED_KEY) or 0)


def _whole(amount):
    """JSON numbers may arrive as 10000.0."""
    return int(amount) if isinstance(amount, float) and amount.is_integer() else amount


def _norm_id(pending_id: str) -> str:
    return (pending_id or "").strip().upper()


def _drop(tool_context: ToolContext, pending_id: str) -> None:
    """Reassign the dict so ADK records the state change."""
    pending = dict(tool_context.state.get(PENDING_KEY) or {})
    pending.pop(pending_id, None)
    tool_context.state[PENDING_KEY] = pending
