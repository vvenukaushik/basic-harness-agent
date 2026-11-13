"""Seed data. Never mutated at runtime: store.py deep-copies it."""

ACCOUNT = {
    "account_id": "ACC-1001",
    "holder_name": "Venu Demo",
    "account_number": "4532001187654321",
    "balance": 200_000,
    "status": "ACTIVE",
    "daily_limit": 100_000,
    "transferred_today": 25_000,
}

BENEFICIARIES = [
    {"beneficiary_id": "BEN-01", "name": "John Smith", "account_number": "7788001122334411", "status": "ACTIVE"},
    {"beneficiary_id": "BEN-02", "name": "John Lewis", "account_number": "7788001122335522", "status": "ACTIVE"},
    {"beneficiary_id": "BEN-03", "name": "Aaron Johnson", "account_number": "7788001122336633", "status": "ACTIVE"},
    {"beneficiary_id": "BEN-04", "name": "Nick Anderson", "account_number": "7788001122337744", "status": "BLOCKED"},
]
