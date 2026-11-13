from banking_agent import mock_data, store, tools
from tests.test_transfer_flow import FakeToolContext as Ctx


def test_mask_keeps_last_four():
    assert store.mask("7788001122334411") == "****4411"


def test_reset_restores_seed_and_does_not_mutate_mock_data():
    store.record_transfer("BEN-01", 10_000)
    assert store.get_account()["balance"] == 190_000
    assert mock_data.ACCOUNT["balance"] == 200_000
    tools.reset_demo_data()
    assert store.get_account()["balance"] == 200_000
    assert store._store["transfers"] == []


def test_transfer_record_shape():
    t = store.record_transfer("BEN-02", 500)
    assert t["transfer_id"].startswith("TXN-") and len(t["transfer_id"]) == 10
    assert store.find_transfer(t["transfer_id"].lower()) == t


def test_no_tool_returns_a_full_account_number():
    full_numbers = [mock_data.ACCOUNT["account_number"]] + [b["account_number"] for b in mock_data.BENEFICIARIES]
    results = [
        tools.check_balance(),
        tools.find_beneficiaries("john"),
        tools.find_beneficiaries("Nick"),
        tools.initiate_transfer(100, Ctx(), beneficiary_name="John Smith"),
        tools.initiate_transfer(100, Ctx(), beneficiary_name="John"),
    ]
    text = repr(results)
    assert not any(n in text for n in full_numbers)


def test_initiate_enforces_policy_and_masks_candidates():
    r = tools.initiate_transfer(10_000, Ctx(), beneficiary_name="John")
    assert r["status"] == "NEEDS_CLARIFICATION" and r["reason"] == "AMBIGUOUS_BENEFICIARY"
    assert r["candidates"] == [
        {"beneficiary_id": "BEN-01", "name": "John Smith", "account": "****4411"},
        {"beneficiary_id": "BEN-02", "name": "John Lewis", "account": "****5522"},
    ]
    r = tools.initiate_transfer(25_000, Ctx(), beneficiary_name="Nick")
    assert (r["status"], r["reason"]) == ("REJECTED", "BENEFICIARY_BLOCKED")
    assert store.get_account()["balance"] == 200_000


def test_initiate_accepts_float_whole_amount():
    r = tools.initiate_transfer(10_000.0, Ctx(), beneficiary_id="BEN-02")
    assert r["status"] == "PENDING_CONFIRMATION" and r["summary"]["amount"] == 10_000
