"""PolicyService: the only place business rules live.

Pure Python. No LLM, no ADK imports, no store access: callers pass the data in.
Returns raw beneficiary dicts; masking is the tool layer's job.
"""
from .models import AccountStatus, PolicyDecision, Reason, TransferStatus


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def match_beneficiaries(query: str, beneficiaries: list[dict]) -> list[dict]:
    """Explicit name matching.

    - Case-insensitive, whitespace trimmed and collapsed.
    - Query equal to a full name -> only that beneficiary.
    - Otherwise every query token must equal a whole token of the name
      ("john" matches John Smith and John Lewis, not Aaron Johnson).
    """
    q = _normalize(query or "")
    if not q:
        return []
    exact = [b for b in beneficiaries if _normalize(b["name"]) == q]
    if exact:
        return exact
    q_tokens = q.split()
    return [b for b in beneficiaries if all(t in _normalize(b["name"]).split() for t in q_tokens)]


def find_by_id(beneficiary_id: str, beneficiaries: list[dict]) -> list[dict]:
    bid = (beneficiary_id or "").strip().upper()
    return [b for b in beneficiaries if b["beneficiary_id"].upper() == bid]


SESSION_TRANSFER_LIMIT = 2


class PolicyService:
    @staticmethod
    def validate_transfer(
        account: dict,
        beneficiaries: list[dict],
        amount: int,
        beneficiary_name: str | None = None,
        beneficiary_id: str | None = None,
        completed_transfers: int = 0,
    ) -> PolicyDecision:
        """Check the rules in order; the first failure wins."""
        # 0. Session transfer limit (Stage 4), checked first.
        if completed_transfers >= SESSION_TRANSFER_LIMIT:
            return _reject(
                Reason.SESSION_TRANSFER_LIMIT,
                f"This session has reached its limit of {SESSION_TRANSFER_LIMIT} transfers. "
                "Start a new session to make another transfer.",
            )

        # 1. Beneficiary exists (by exact id if given, else by name).
        if beneficiary_id:
            matches = find_by_id(beneficiary_id, beneficiaries)
            label = beneficiary_id
        else:
            matches = match_beneficiaries(beneficiary_name or "", beneficiaries)
            label = beneficiary_name or ""
        if not matches:
            return _reject(Reason.BENEFICIARY_NOT_FOUND, f"No saved beneficiary matches '{label}'.")

        # 2. Beneficiary is unambiguous.
        if len(matches) > 1:
            return PolicyDecision(
                status=TransferStatus.NEEDS_CLARIFICATION,
                reason=Reason.AMBIGUOUS_BENEFICIARY,
                message=f"Multiple beneficiaries match '{label}'. Ask the user which one.",
                candidates=matches,
            )
        beneficiary = matches[0]

        # 3. Amount is a positive whole number.
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            return _reject(Reason.INVALID_AMOUNT, "The amount must be a positive whole number of USD.", beneficiary)

        # 4. Source account active.
        if account["status"] != AccountStatus.ACTIVE.value:
            return _reject(Reason.ACCOUNT_INACTIVE, "The source account is not active.", beneficiary)

        # 5. Beneficiary account active.
        if beneficiary["status"] != AccountStatus.ACTIVE.value:
            return _reject(
                Reason.BENEFICIARY_BLOCKED,
                f"{beneficiary['name']}'s account is blocked. Transfers to it are not allowed.",
                beneficiary,
            )

        # 6. Sufficient balance.
        if amount > account["balance"]:
            return _reject(
                Reason.INSUFFICIENT_FUNDS,
                f"Insufficient funds. Available balance is {account['balance']}.",
                beneficiary,
            )

        # 7. Daily limit.
        remaining = account["daily_limit"] - account["transferred_today"]
        if account["transferred_today"] + amount > account["daily_limit"]:
            return _reject(
                Reason.DAILY_LIMIT_EXCEEDED,
                f"This exceeds the daily transfer limit. Remaining allowance today is {remaining}.",
                beneficiary,
            )

        # 8. All checks passed.
        return PolicyDecision(status=TransferStatus.APPROVED, message="Transfer approved.", beneficiary=beneficiary)


def _reject(reason: Reason, message: str, beneficiary: dict | None = None) -> PolicyDecision:
    return PolicyDecision(status=TransferStatus.REJECTED, reason=reason, message=message, beneficiary=beneficiary)


# ---------------------------------------------------------------------------
# Stage 3: confirmation guards for a pending transfer.
# ---------------------------------------------------------------------------

PENDING_TTL_SECONDS = 5 * 60


def check_confirmation(
    pending: dict | None,
    pending_id: str,
    now: float,
    invocation_id: str,
) -> PolicyDecision | None:
    """Guards for confirm_transfer. Returns a rejection, or None if they all pass.

    1. Pending ID exists in this session's state (an entry is removed once
       confirmed or cancelled, which also makes it single use).
    2. Not expired.
    4. Confirmed in a later user turn than the one that initiated it.
    Guard 5 (re-validation) is validate_transfer() run again by the caller.
    """
    if pending is None:
        return _reject(Reason.PENDING_NOT_FOUND, f"No pending transfer with ID '{pending_id}'. Nothing was moved.")
    if now - pending["created_at"] > PENDING_TTL_SECONDS:
        return _reject(Reason.PENDING_EXPIRED, "This pending transfer has expired. Nothing was moved.")
    if pending["invocation_id"] == invocation_id:
        return _reject(
            Reason.CONFIRMATION_SAME_TURN,
            "The user must confirm in a separate message. The transfer is still pending; "
            "show the user the details and ask them to confirm.",
        )
    return None
