from banking_agent import mock_data
from banking_agent.policy import PolicyService, find_by_id, match_beneficiaries

BENS = mock_data.BENEFICIARIES


def names(matches):
    return sorted(b["name"] for b in matches)


def test_john_matches_two_johns_not_aaron_johnson():
    assert names(match_beneficiaries("john", BENS)) == ["John Lewis", "John Smith"]


def test_full_name_is_exact():
    assert names(match_beneficiaries("John Smith", BENS)) == ["John Smith"]


def test_case_and_whitespace_are_ignored():
    assert names(match_beneficiaries("  jOhN   sMiTh ", BENS)) == ["John Smith"]


def test_last_name_token():
    assert names(match_beneficiaries("Johnson", BENS)) == ["Aaron Johnson"]


def test_partial_token_does_not_match():
    assert match_beneficiaries("Joh", BENS) == []


def test_unknown_name():
    assert match_beneficiaries("Alice", BENS) == []


def test_empty_query():
    assert match_beneficiaries("   ", BENS) == []


def test_match_by_beneficiary_id_is_exact():
    assert names(find_by_id("ben-02", BENS)) == ["John Lewis"]
    assert find_by_id("BEN-9", BENS) == []


def test_transfer_by_id_resolves_ambiguity():
    import copy
    account = copy.deepcopy(mock_data.ACCOUNT)
    d = PolicyService.validate_transfer(account, BENS, 10_000, beneficiary_name="John", beneficiary_id="BEN-02")
    assert d.status.value == "APPROVED" and d.beneficiary["name"] == "John Lewis"
