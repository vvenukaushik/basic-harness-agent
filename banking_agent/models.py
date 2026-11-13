"""Statuses, reasons and the policy decision type. No business logic here."""
from dataclasses import dataclass, field
from enum import Enum


class TransferStatus(str, Enum):
    APPROVED = "APPROVED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    REJECTED = "REJECTED"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class Reason(str, Enum):
    BENEFICIARY_NOT_FOUND = "BENEFICIARY_NOT_FOUND"
    AMBIGUOUS_BENEFICIARY = "AMBIGUOUS_BENEFICIARY"
    INVALID_AMOUNT = "INVALID_AMOUNT"
    ACCOUNT_INACTIVE = "ACCOUNT_INACTIVE"
    BENEFICIARY_BLOCKED = "BENEFICIARY_BLOCKED"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    DAILY_LIMIT_EXCEEDED = "DAILY_LIMIT_EXCEEDED"
    PENDING_NOT_FOUND = "PENDING_NOT_FOUND"
    PENDING_EXPIRED = "PENDING_EXPIRED"
    CONFIRMATION_SAME_TURN = "CONFIRMATION_SAME_TURN"
    SESSION_TRANSFER_LIMIT = "SESSION_TRANSFER_LIMIT"


class AccountStatus(str, Enum):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class PolicyDecision:
    status: TransferStatus
    reason: Reason | None = None
    message: str = ""
    beneficiary: dict | None = None          # the resolved beneficiary (raw, unmasked)
    candidates: list[dict] = field(default_factory=list)  # raw, unmasked
