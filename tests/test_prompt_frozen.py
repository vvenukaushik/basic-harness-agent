import hashlib

from banking_agent.prompt import SYSTEM_PROMPT

# Recorded at Stage 1. Never update this value: if the test fails, revert the prompt.
STAGE_1_PROMPT_SHA256 = "c45525a96e5f6ccff6e2522e71e284c767b7f5790bc4a7b423019f0f389f1872"


def test_system_prompt_is_frozen():
    assert hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest() == STAGE_1_PROMPT_SHA256
