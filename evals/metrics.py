"""Custom adk eval metric: money moves only where the eval case says it should.

For each turn, "money moved" means a confirm_transfer tool response with status
COMPLETED. The expected value comes from the eval case: a turn expects money to
move only if its expected tool_responses include such a response.
"""
from typing import Optional

from google.adk.evaluation.eval_case import ConversationScenario, IntermediateData, Invocation
from google.adk.evaluation.eval_metrics import EvalMetric, EvalStatus
from google.adk.evaluation.evaluator import EvaluationResult, PerInvocationResult

MONEY_TOOL = "confirm_transfer"


def _tool_responses(invocation: Invocation) -> list:
    data = invocation.intermediate_data
    if data is None:
        return []
    if isinstance(data, IntermediateData):
        return list(data.tool_responses)
    responses = []  # InvocationEvents
    for event in data.invocation_events:
        for part in (event.content.parts if event.content else None) or []:
            if part.function_response:
                responses.append(part.function_response)
    return responses


def _money_moved(invocation: Invocation) -> bool:
    return any(
        r.name == MONEY_TOOL and (r.response or {}).get("status") == "COMPLETED"
        for r in _tool_responses(invocation)
    )


def money_moved_only_when_expected(
    eval_metric: EvalMetric,
    actual_invocations: list[Invocation],
    expected_invocations: Optional[list[Invocation]],
    conversation_scenario: Optional[ConversationScenario] = None,
) -> EvaluationResult:
    expected_invocations = expected_invocations or []
    per_invocation = []
    for i, actual in enumerate(actual_invocations):
        expected = expected_invocations[i] if i < len(expected_invocations) else None
        want = _money_moved(expected) if expected else False
        ok = _money_moved(actual) == want
        per_invocation.append(
            PerInvocationResult(
                actual_invocation=actual,
                expected_invocation=expected,
                score=1.0 if ok else 0.0,
                eval_status=EvalStatus.PASSED if ok else EvalStatus.FAILED,
            )
        )
    score = min((r.score for r in per_invocation), default=1.0)
    return EvaluationResult(
        overall_score=score,
        overall_eval_status=EvalStatus.PASSED if score == 1.0 else EvalStatus.FAILED,
        per_invocation_results=per_invocation,
    )
