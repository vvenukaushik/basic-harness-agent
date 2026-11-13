"""initiate -> confirm / cancel flow, with a fake ToolContext (no ADK runner, no LLM)."""
import pytest

from banking_agent import store, tools
from banking_agent.policy import PENDING_TTL_SECONDS


class FakeSession:
    def __init__(self, session_id: str):
        self.id = session_id


class FakeToolContext:
    _count = 0

    def __init__(self):
        FakeToolContext._count += 1
        self.state: dict = {}
        self.invocation_id = "inv-1"
        self.session = FakeSession(f"session-{FakeToolContext._count}")

    def next_turn(self):
        n = int(self.invocation_id.split("-")[1]) + 1
        self.invocation_id = f"inv-{n}"


@pytest.fixture
def ctx():
    return FakeToolContext()


@pytest.fixture
def clock(monkeypatch):
    t = {"now": 1_000_000.0}
    monkeypatch.setattr(tools, "_now", lambda: t["now"])
    return t


def balance():
    return store.get_account()["balance"]


def initiate(ctx, amount=10_000, **kw):
    kw.setdefault("beneficiary_name", "John Smith")
    return tools.initiate_transfer(amount, ctx, **kw)


def test_initiate_moves_no_money(ctx):
    r = initiate(ctx)
    assert r["status"] == "PENDING_CONFIRMATION"
    assert r["pending_id"].startswith("PND-")
    assert r["summary"] == {
        "to": {"beneficiary_id": "BEN-01", "name": "John Smith", "account": "****4411", "status": "ACTIVE"},
        "amount": 10_000,
    }
    assert balance() == 200_000


def test_happy_path(ctx):
    pid = initiate(ctx)["pending_id"]
    ctx.next_turn()
    r = tools.confirm_transfer(pid, ctx)
    assert r["status"] == "COMPLETED"
    assert r["new_balance"] == 190_000 == balance()
    assert store.find_transfer(r["transfer_id"])["beneficiary_id"] == "BEN-01"


def test_initiate_runs_policy(ctx):
    r = initiate(ctx, 25_000, beneficiary_name="Nick")
    assert (r["status"], r["reason"]) == ("REJECTED", "BENEFICIARY_BLOCKED")
    r = initiate(ctx, beneficiary_name="John")
    assert r["status"] == "NEEDS_CLARIFICATION"
    assert ctx.state.get(tools.PENDING_KEY, {}) == {}


def test_confirm_unknown_id(ctx):
    r = tools.confirm_transfer("PND-123", ctx)
    assert (r["status"], r["reason"]) == ("REJECTED", "PENDING_NOT_FOUND")
    assert balance() == 200_000


def test_confirm_same_invocation_is_rejected_and_stays_pending(ctx):
    pid = initiate(ctx)["pending_id"]
    r = tools.confirm_transfer(pid, ctx)  # same turn: "skip confirmation"
    assert (r["status"], r["reason"]) == ("REJECTED", "CONFIRMATION_SAME_TURN")
    assert balance() == 200_000
    ctx.next_turn()
    assert tools.confirm_transfer(pid, ctx)["status"] == "COMPLETED"


def test_confirm_expired(ctx, clock):
    pid = initiate(ctx)["pending_id"]
    ctx.next_turn()
    clock["now"] += PENDING_TTL_SECONDS + 1
    r = tools.confirm_transfer(pid, ctx)
    assert r["reason"] == "PENDING_EXPIRED"
    assert balance() == 200_000
    assert tools.confirm_transfer(pid, ctx)["reason"] == "PENDING_NOT_FOUND"


def test_confirm_just_before_expiry(ctx, clock):
    pid = initiate(ctx)["pending_id"]
    ctx.next_turn()
    clock["now"] += PENDING_TTL_SECONDS
    assert tools.confirm_transfer(pid, ctx)["status"] == "COMPLETED"


def test_confirm_is_single_use(ctx):
    pid = initiate(ctx)["pending_id"]
    ctx.next_turn()
    assert tools.confirm_transfer(pid, ctx)["status"] == "COMPLETED"
    ctx.next_turn()
    r = tools.confirm_transfer(pid, ctx)
    assert r["reason"] == "PENDING_NOT_FOUND"
    assert balance() == 190_000


def test_confirm_revalidates_against_current_state(ctx):
    pid = initiate(ctx, 70_000)["pending_id"]
    store.record_transfer("BEN-02", 10_000)  # state changes between initiate and confirm
    ctx.next_turn()
    r = tools.confirm_transfer(pid, ctx)
    assert (r["status"], r["reason"]) == ("REJECTED", "DAILY_LIMIT_EXCEEDED")
    assert balance() == 190_000


def test_confirm_revalidates_blocked_beneficiary(ctx):
    pid = initiate(ctx)["pending_id"]
    store.get_beneficiaries()[0]["status"] = "BLOCKED"
    ctx.next_turn()
    assert tools.confirm_transfer(pid, ctx)["reason"] == "BENEFICIARY_BLOCKED"


def test_cancel(ctx):
    pid = initiate(ctx)["pending_id"]
    ctx.next_turn()
    assert tools.cancel_transfer(pid, ctx)["status"] == "CANCELLED"
    ctx.next_turn()
    assert tools.confirm_transfer(pid, ctx)["reason"] == "PENDING_NOT_FOUND"
    assert balance() == 200_000


def test_cancel_unknown(ctx):
    assert tools.cancel_transfer("PND-NOPE", ctx)["reason"] == "PENDING_NOT_FOUND"


def test_pending_ids_are_per_session(ctx):
    pid = initiate(ctx)["pending_id"]
    other = FakeToolContext()
    other.invocation_id = "inv-99"
    assert tools.confirm_transfer(pid, other)["reason"] == "PENDING_NOT_FOUND"


def confirm_new(ctx, amount=10_000):
    pid = initiate(ctx, amount)["pending_id"]
    ctx.next_turn()
    r = tools.confirm_transfer(pid, ctx)
    ctx.next_turn()
    return r


def test_session_limit_third_transfer_rejected(ctx):
    assert confirm_new(ctx)["status"] == "COMPLETED"
    assert confirm_new(ctx)["status"] == "COMPLETED"
    r = initiate(ctx)
    assert (r["status"], r["reason"]) == ("REJECTED", "SESSION_TRANSFER_LIMIT")
    assert balance() == 180_000


def test_session_limit_also_enforced_at_confirm(ctx):
    """Three pendings opened before any confirm cannot all go through."""
    pids = [initiate(ctx, 1_000)["pending_id"] for _ in range(3)]
    ctx.next_turn()
    results = [tools.confirm_transfer(p, ctx) for p in pids]
    assert [r["status"] for r in results] == ["COMPLETED", "COMPLETED", "REJECTED"]
    assert results[2]["reason"] == "SESSION_TRANSFER_LIMIT"
    assert balance() == 198_000


def test_new_session_can_transfer_again(ctx):
    confirm_new(ctx)
    confirm_new(ctx)
    other = FakeToolContext()
    assert confirm_new(other)["status"] == "COMPLETED"


def test_rejected_confirm_does_not_count_towards_limit(ctx):
    pid = initiate(ctx, 70_000)["pending_id"]
    store.record_transfer("BEN-02", 10_000)
    ctx.next_turn()
    assert tools.confirm_transfer(pid, ctx)["status"] == "REJECTED"
    assert ctx.state.get(tools.COMPLETED_KEY, 0) == 0


def test_pending_id_is_case_insensitive(ctx):
    pid = initiate(ctx)["pending_id"]
    ctx.next_turn()
    assert tools.confirm_transfer(f"  {pid.lower()} ", ctx)["status"] == "COMPLETED"
