"""In-memory mock store. The only module that sees full account numbers."""
import copy
import secrets
from datetime import datetime, timezone

from . import mock_data

_store: dict = {}


def reset_store() -> None:
    """Restore the seed data and clear all transfers."""
    _store.clear()
    _store["account"] = copy.deepcopy(mock_data.ACCOUNT)
    _store["beneficiaries"] = copy.deepcopy(mock_data.BENEFICIARIES)
    _store["transfers"] = []


def mask(number: str) -> str:
    """'7788001122334411' -> '****4411'."""
    return "****" + number[-4:]


def public_beneficiary(b: dict) -> dict:
    """A beneficiary as it may be shown to the model (masked number)."""
    return {
        "beneficiary_id": b["beneficiary_id"],
        "name": b["name"],
        "account": mask(b["account_number"]),
        "status": b["status"],
    }


def get_account() -> dict:
    return _store["account"]


def get_beneficiaries() -> list[dict]:
    return _store["beneficiaries"]


def record_transfer(beneficiary_id: str, amount: int) -> dict:
    """Deduct the amount and append a completed transfer record."""
    account = _store["account"]
    account["balance"] -= amount
    account["transferred_today"] += amount
    transfer = {
        "transfer_id": f"TXN-{secrets.token_hex(3).upper()}",
        "beneficiary_id": beneficiary_id,
        "amount": amount,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "COMPLETED",
    }
    _store["transfers"].append(transfer)
    return transfer


def find_transfer(transfer_id: str) -> dict | None:
    for t in _store["transfers"]:
        if t["transfer_id"].upper() == transfer_id.strip().upper():
            return t
    return None


reset_store()
