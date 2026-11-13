"""Root agent definition. The prompt and model never change after Stage 1."""
import os

from dotenv import load_dotenv
from google.adk.agents import Agent

from . import audit
from .prompt import SYSTEM_PROMPT
from .tools import (
    cancel_transfer,
    check_balance,
    confirm_transfer,
    find_beneficiaries,
    get_audit_log,
    get_transfer_status,
    initiate_transfer,
    reset_demo_data,
)

load_dotenv()

MODEL_NAME = os.getenv("MODEL_NAME", "gemini-3.5-flash-lite")

root_agent = Agent(
    name="banking_agent",
    model=MODEL_NAME,
    instruction=SYSTEM_PROMPT,
    tools=[
        check_balance,
        find_beneficiaries,
        initiate_transfer,
        confirm_transfer,
        cancel_transfer,
        get_transfer_status,
        get_audit_log,
        reset_demo_data,
    ],
    before_model_callback=audit.before_model_callback,
    before_tool_callback=audit.before_tool_callback,
    after_tool_callback=audit.after_tool_callback,
)
