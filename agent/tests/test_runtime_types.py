"""Tests for runtime type definitions."""

from src.runtime.types import Action, HookAction, RunContext, TurnResult


def test_turn_result_creation():
    result = TurnResult(
        messages=[{"role": "assistant", "content": "hello"}],
        usage={"input_tokens": 100, "output_tokens": 50},
        iterations=1,
    )
    assert result.iterations == 1
    assert len(result.messages) == 1


def test_run_context_creation():
    ctx = RunContext(
        conversation_id="conv-1",
        session_id="sess-1",
        user_id="user-1",
        iteration=0,
        tool_history=[],
        messages=[],
    )
    assert ctx.conversation_id == "conv-1"


def test_hook_action_continue():
    action = HookAction.continue_with({"query": "test"})
    assert action.kind == "continue" and action.modified_input == {"query": "test"}


def test_hook_action_deny():
    action = HookAction.deny("rate limited")
    assert action.kind == "deny" and action.reason == "rate limited"


def test_hook_action_escalate():
    action = HookAction.escalate("stuck")
    assert action.kind == "escalate" and action.message == "stuck"


def test_action_continue():
    assert Action.keep_going().kind == "continue"


def test_action_inject_guidance():
    a = Action.inject_guidance("try different")
    assert a.kind == "inject_guidance" and a.message == "try different"


def test_action_escalate_to_user():
    a = Action.escalate_to_user(tried=["web_search x3"], suggestion="Try SEC?")
    assert a.kind == "escalate_to_user" and len(a.tried) == 1


def test_action_hard_stop():
    a = Action.hard_stop("max iterations")
    assert a.kind == "hard_stop" and a.reason == "max iterations"
