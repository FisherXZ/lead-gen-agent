"""Tests for request_guidance tool module."""

from __future__ import annotations

import pytest

from src.tools.request_guidance import DEFINITION, execute

# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------


class TestDefinition:
    def test_name(self):
        assert DEFINITION["name"] == "request_guidance"

    def test_required_fields(self):
        assert "status_summary" in DEFINITION["input_schema"]["required"]
        assert "question" in DEFINITION["input_schema"]["required"]

    def test_options_is_optional(self):
        assert "options" not in DEFINITION["input_schema"].get("required", [])


# ---------------------------------------------------------------------------
# execute() function
# ---------------------------------------------------------------------------


class TestExecute:
    @pytest.mark.asyncio
    async def test_echoes_input_back(self):
        result = await execute(
            {
                "status_summary": "Found two possible EPCs.",
                "question": "Which one seems more likely?",
                "options": ["Blattner", "McCarthy"],
            }
        )

        assert result["status_summary"] == "Found two possible EPCs."
        assert result["question"] == "Which one seems more likely?"
        assert result["options"] == ["Blattner", "McCarthy"]
        assert result["awaiting_response"] is True

    @pytest.mark.asyncio
    async def test_missing_options_defaults_to_empty(self):
        result = await execute(
            {
                "status_summary": "Stuck.",
                "question": "Any leads?",
            }
        )

        assert result["options"] == []
        assert result["awaiting_response"] is True

    @pytest.mark.asyncio
    async def test_empty_input_graceful(self):
        result = await execute({})

        assert result["status_summary"] == ""
        assert result["question"] == ""
        assert result["options"] == []
        assert result["awaiting_response"] is True


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


class TestRegistryIntegration:
    def test_registered_in_all_tools(self):
        from src.tools import get_tool_names

        assert "request_guidance" in get_tool_names()

    @pytest.mark.asyncio
    async def test_execute_via_registry(self):
        from src.tools import execute_tool

        result = await execute_tool(
            "request_guidance",
            {
                "status_summary": "Found conflicting info.",
                "question": "Should I trust the trade pub or the PR?",
                "options": ["Trade publication", "Press release"],
            },
        )

        assert result["awaiting_response"] is True
        assert result["question"] == "Should I trust the trade pub or the PR?"

    def test_not_in_research_tools(self):
        """request_guidance should NOT be available in batch research."""
        from src.research import RESEARCH_TOOLS

        assert "request_guidance" not in RESEARCH_TOOLS
