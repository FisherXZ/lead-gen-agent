"""Tests for EscalationPolicy."""
import json, pytest
from agent.src.runtime.escalation import EscalationPolicy

def _tool_result_msg(name, content):
    return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"id-{name}", "content": content}]}

def _assistant_msg(name):
    return {"role": "assistant", "content": [{"type": "tool_use", "id": f"id-{name}", "name": name, "input": {}}]}

def test_continue_under_limits():
    p = EscalationPolicy(max_iterations=50, stagnation_window=4)
    msgs = [_assistant_msg("web_search"), _tool_result_msg("web_search", json.dumps({"results": [{"title": "SunPower EPC project"}]}))]
    assert p.evaluate(msgs, 2, ["web_search"]).kind == "continue"

def test_hard_stop():
    assert EscalationPolicy(max_iterations=10).evaluate([], 10, []).kind == "hard_stop"

def test_stagnation_user_mode():
    p = EscalationPolicy(max_iterations=50, stagnation_window=4, escalation_mode="user", min_iterations_before_stagnation=0)
    msgs = []
    for _ in range(4):
        msgs += [_assistant_msg("web_search"), _tool_result_msg("web_search", json.dumps({"results": []}))]
    assert p.evaluate(msgs, 8, ["web_search"] * 8).kind == "escalate_to_user"

def test_stagnation_autonomous():
    p = EscalationPolicy(max_iterations=50, stagnation_window=4, escalation_mode="autonomous", min_iterations_before_stagnation=0)
    msgs = []
    for _ in range(4):
        msgs += [_assistant_msg("web_search"), _tool_result_msg("web_search", json.dumps({"results": []}))]
    assert p.evaluate(msgs, 8, ["web_search"] * 8).kind == "inject_guidance"

def test_no_stagnation_with_signals():
    p = EscalationPolicy(max_iterations=50, stagnation_window=4, min_iterations_before_stagnation=0)
    msgs = []
    for co in ["SunPower Corp", "NextEra Energy", "Blattner Energy", "Mortenson Construction"]:
        msgs += [_assistant_msg("web_search"), _tool_result_msg("web_search", json.dumps({"results": [{"title": f"{co} wins EPC"}]}))]
    assert p.evaluate(msgs, 8, ["web_search"] * 4).kind == "continue"

def test_consecutive_errors():
    p = EscalationPolicy(max_iterations=50, stagnation_window=4, escalation_mode="user")
    msgs = []
    for _ in range(3):
        msgs += [_assistant_msg("web_search"), _tool_result_msg("web_search", json.dumps({"error": "500"}))]
    assert p.evaluate(msgs, 5, ["web_search"] * 3).kind == "escalate_to_user"

def test_min_iterations_before_stagnation():
    p = EscalationPolicy(max_iterations=50, stagnation_window=4, min_iterations_before_stagnation=6)
    msgs = []
    for _ in range(4):
        msgs += [_assistant_msg("web_search"), _tool_result_msg("web_search", json.dumps({"results": []}))]
    assert p.evaluate(msgs, 3, ["web_search"] * 3).kind == "continue"
