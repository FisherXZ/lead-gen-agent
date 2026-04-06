"""Escalation policy for the agent runtime.

Replaces hard iteration caps with signal-based stopping. Detects
stagnation (tools not producing new information) and consecutive
errors, then either escalates to the user or injects guidance.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter

from .types import Action

_logger = logging.getLogger(__name__)

# Patterns that suggest new, relevant information was found
_MAX_SEEN_SIGNALS = 500


def _extract_signals(text: str) -> set[str]:
    """Extract meaningful entity-like tokens from text."""
    # Simple heuristic: capitalized multi-word phrases (likely company names)
    entities = set(re.findall(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+", text))
    return entities


def _get_recent_tool_results(messages: list[dict], window: int) -> list[str]:
    """Extract the last N tool result content strings from messages."""
    results = []
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                results.append(block.get("content", ""))
                if len(results) >= window:
                    return results
    return results


def _count_consecutive_errors(messages: list[dict]) -> int:
    """Count consecutive tool errors from the end of the conversation."""
    count = 0
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            break
        has_tool_result = False
        all_errors = True
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                has_tool_result = True
                result_str = block.get("content", "")
                try:
                    parsed = json.loads(result_str)
                    if not (isinstance(parsed, dict) and "error" in parsed):
                        all_errors = False
                except (json.JSONDecodeError, TypeError):
                    all_errors = False
        if has_tool_result and all_errors:
            count += 1
        elif has_tool_result:
            break
    return count


class EscalationPolicy:
    """Signal-based escalation policy."""

    def __init__(
        self,
        max_iterations: int = 50,
        stagnation_window: int = 4,
        escalation_mode: str = "user",
        min_iterations_before_stagnation: int = 6,
    ):
        self.max_iterations = max_iterations
        self.stagnation_window = stagnation_window
        self.escalation_mode = escalation_mode
        self.min_iterations_before_stagnation = min_iterations_before_stagnation
        self._seen_signals: set[str] = set()

    def evaluate(
        self,
        messages: list[dict],
        iteration: int,
        tool_history: list[str],
    ) -> Action:
        """Evaluate whether the agent should continue, get guidance, or stop."""
        # 1. Hard safety limit
        if iteration >= self.max_iterations:
            return Action.hard_stop("max iterations reached")

        # 2. Consecutive errors
        consecutive_errors = _count_consecutive_errors(messages)
        if consecutive_errors >= 3:
            tried = _summarize_tool_usage(tool_history)
            if self.escalation_mode == "user":
                return Action.escalate_to_user(
                    tried=tried,
                    suggestion=(
                        f"{consecutive_errors} consecutive tool errors. "
                        "Want me to continue or try a different approach?"
                    ),
                )
            else:
                return Action.inject_guidance(
                    f"{consecutive_errors} consecutive tool errors. "
                    "Switch to a different tool or approach."
                )

        # 3. Stagnation detection (only after minimum iterations)
        if iteration >= self.min_iterations_before_stagnation:
            recent_results = _get_recent_tool_results(messages, self.stagnation_window)
            if len(recent_results) >= self.stagnation_window and self._is_stagnating(
                recent_results
            ):
                tried = _summarize_tool_usage(tool_history)
                if self.escalation_mode == "user":
                    return Action.escalate_to_user(
                        tried=tried,
                        suggestion=(
                            "Recent searches aren't producing new leads. "
                            "Should I try a different angle?"
                        ),
                    )
                else:
                    return Action.inject_guidance(
                        "Recent searches returning diminishing results. "
                        "Switch to an untried source category."
                    )

        # 4. All good
        return Action.keep_going()

    def _is_stagnating(self, recent_results: list[str]) -> bool:
        """Check if recent tool results contain new signals."""
        new_signal_count = 0
        for result_str in recent_results:
            # Check for empty results
            try:
                parsed = json.loads(result_str)
                if isinstance(parsed, dict):
                    results_list = parsed.get("results", [])
                    if isinstance(results_list, list) and len(results_list) == 0:
                        continue  # empty results, no new signals
            except (json.JSONDecodeError, TypeError):
                pass

            signals = _extract_signals(result_str)
            new_signals = signals - self._seen_signals
            if new_signals:
                new_signal_count += 1
                self._seen_signals.update(new_signals)
                # Cap to prevent unbounded growth
                if len(self._seen_signals) > _MAX_SEEN_SIGNALS:
                    # Keep only the most recent half
                    excess = len(self._seen_signals) - _MAX_SEEN_SIGNALS // 2
                    for _ in range(excess):
                        self._seen_signals.pop()

        # Stagnating if fewer than 25% of recent results had new signals
        return new_signal_count / len(recent_results) < 0.25


def _summarize_tool_usage(tool_history: list[str]) -> list[str]:
    """Summarize which tools were used and how many times."""
    counts = Counter(tool_history)
    return [f"{name} x{count}" for name, count in counts.most_common()]
