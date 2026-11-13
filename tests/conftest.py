import pytest

from banking_agent import audit, store


@pytest.fixture(autouse=True)
def fresh_store():
    """Every test starts from the seed data."""
    store.reset_store()
    yield
    store.reset_store()


@pytest.fixture(autouse=True)
def isolated_audit_log(tmp_path, monkeypatch):
    """Audit events go to a temp file and an empty in-memory log."""
    monkeypatch.setenv(audit.AUDIT_FILE_ENV, str(tmp_path / "audit.jsonl"))
    audit.clear()
    yield tmp_path / "audit.jsonl"
    audit.clear()
