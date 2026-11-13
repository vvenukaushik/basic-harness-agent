import copy

import pytest

from banking_agent import mock_data
from banking_agent.models import Reason, TransferStatus
from banking_agent.policy import PolicyService


@pytest.fixture
def account():
    return copy.deepcopy(mock_data.ACCOUNT)


@pytest.fixture
def bens():
    return copy.deepcopy(mock_data.BENEFICIARIES)


def validate(account, bens, amount, name=None, bid=None):
    return PolicyService.validate_transfer(account, bens, amount, beneficiary_name=name, beneficiary_id=bid)


# Rule 1
def test_beneficiary_not_found(account, bens):
    d = validate(account, bens, 100, name="Alice")
    assert (d.status, d.reason) == (TransferStatus.REJECTED, Reason.BENEFICIARY_NOT_FOUND)


def test_unknown_beneficiary_id(account, bens):
    d = validate(account, bens, 100, bid="BEN-99")
    assert d.reason == Reason.BENEFICIARY_NOT_FOUND


# Rule 2
def test_ambiguous_beneficiary(account, bens):
    d = validate(account, bens, 10_000, name="John")
    assert (d.status, d.reason) == (TransferStatus.NEEDS_CLARIFICATION, Reason.AMBIGUOUS_BENEFICIARY)
    assert sorted(c["beneficiary_id"] for c in d.candidates) == ["BEN-01", "BEN-02"]


# Rule 3
@pytest.mark.parametrize("amount", [0, -500, 10.5, True, "100"])
def test_invalid_amount(account, bens, amount):
    d = validate(account, bens, amount, name="John Smith")
    assert (d.status, d.reason) == (TransferStatus.REJECTED, Reason.INVALID_AMOUNT)


# Rule 4
def test_source_account_inactive(account, bens):
    account["status"] = "BLOCKED"
    d = validate(account, bens, 100, name="John Smith")
    assert d.reason == Reason.ACCOUNT_INACTIVE


# Rule 5
def test_beneficiary_blocked(account, bens):
    d = validate(account, bens, 25_000, name="Nick")
    assert (d.status, d.reason) == (TransferStatus.REJECTED, Reason.BENEFICIARY_BLOCKED)


# Rule 6
def test_insufficient_funds(account, bens):
    account["balance"] = 1_000
    d = validate(account, bens, 5_000, name="John Smith")
    assert d.reason == Reason.INSUFFICIENT_FUNDS


# Rule 7
def test_daily_limit_exceeded_reports_remaining(account, bens):
    d = validate(account, bens, 90_000, name="John Smith")
    assert d.reason == Reason.DAILY_LIMIT_EXCEEDED
    assert "75000" in d.message


def test_daily_limit_boundary_is_allowed(account, bens):
    assert validate(account, bens, 75_000, name="John Smith").status == TransferStatus.APPROVED
    assert validate(account, bens, 75_001, name="John Smith").reason == Reason.DAILY_LIMIT_EXCEEDED


# Rule 8
def test_approved(account, bens):
    d = validate(account, bens, 10_000, name="John Smith")
    assert d.status == TransferStatus.APPROVED
    assert d.beneficiary["beneficiary_id"] == "BEN-01"


# Rule order: first failure wins
def test_not_found_beats_invalid_amount(account, bens):
    assert validate(account, bens, -5, name="Alice").reason == Reason.BENEFICIARY_NOT_FOUND


def test_ambiguity_beats_invalid_amount(account, bens):
    assert validate(account, bens, -5, name="John").reason == Reason.AMBIGUOUS_BENEFICIARY


def test_invalid_amount_beats_blocked_beneficiary(account, bens):
    assert validate(account, bens, -500, name="Nick").reason == Reason.INVALID_AMOUNT


def test_inactive_account_beats_blocked_beneficiary(account, bens):
    account["status"] = "BLOCKED"
    assert validate(account, bens, 100, name="Nick").reason == Reason.ACCOUNT_INACTIVE


def test_blocked_beats_insufficient_funds(account, bens):
    assert validate(account, bens, 999_999, name="Nick").reason == Reason.BENEFICIARY_BLOCKED


def test_insufficient_funds_beats_daily_limit(account, bens):
    account["balance"] = 50_000
    assert validate(account, bens, 80_000, name="John Smith").reason == Reason.INSUFFICIENT_FUNDS


# Session limit (Stage 4)
def test_session_limit(account, bens):
    ok = PolicyService.validate_transfer(account, bens, 100, beneficiary_name="John Smith", completed_transfers=1)
    assert ok.status == TransferStatus.APPROVED
    d = PolicyService.validate_transfer(account, bens, 100, beneficiary_name="John Smith", completed_transfers=2)
    assert (d.status, d.reason) == (TransferStatus.REJECTED, Reason.SESSION_TRANSFER_LIMIT)


def test_session_limit_is_checked_first(account, bens):
    d = PolicyService.validate_transfer(account, bens, -5, beneficiary_name="Alice", completed_transfers=2)
    assert d.reason == Reason.SESSION_TRANSFER_LIMIT


def test_policy_does_not_mutate_inputs(account, bens):
    before = (copy.deepcopy(account), copy.deepcopy(bens))
    validate(account, bens, 10_000, name="John Smith")
    assert (account, bens) == before
