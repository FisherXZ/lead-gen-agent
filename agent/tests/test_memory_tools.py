"""Tests for remember and recall tool modules."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.tools.remember import DEFINITION as REMEMBER_DEF, execute as remember_execute
from src.tools.recall import DEFINITION as RECALL_DEF, execute as recall_execute


# ---------------------------------------------------------------------------
# remember tool
# ---------------------------------------------------------------------------

class TestRememberDefinition:
    def test_name(self):
        assert REMEMBER_DEF["name"] == "remember"

    def test_required_fields(self):
        assert "memory" in REMEMBER_DEF["input_schema"]["required"]
        assert "scope" in REMEMBER_DEF["input_schema"]["required"]


class TestRememberExecute:
    @pytest.mark.asyncio
    @patch("src.db.save_memory")
    async def test_remember_stores_to_db(self, mock_save):
        mock_save.return_value = {"id": "abc-123"}

        result = await remember_execute({
            "memory": "Blattner is the EPC for Lone Star Solar",
            "scope": "global",
            "memory_key": "blattner-lone-star",
            "importance": 8,
        })

        mock_save.assert_called_once_with(
            memory="Blattner is the EPC for Lone Star Solar",
            scope="global",
            memory_key="blattner-lone-star",
            importance=8,
            conversation_id=None,
            project_id=None,
        )
        assert result["status"] == "remembered"
        assert result["id"] == "abc-123"

    @pytest.mark.asyncio
    async def test_remember_empty_rejected(self):
        result = await remember_execute({"memory": "", "scope": "global"})
        assert "error" in result
        assert "empty" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_remember_whitespace_only_rejected(self):
        result = await remember_execute({"memory": "   ", "scope": "global"})
        assert "error" in result

    @pytest.mark.asyncio
    @patch("src.db.save_memory")
    async def test_remember_truncates_long(self, mock_save):
        mock_save.return_value = {"id": "trunc-123"}
        long_memory = "x" * 3000

        await remember_execute({"memory": long_memory, "scope": "global"})

        call_args = mock_save.call_args
        assert len(call_args.kwargs["memory"]) == 2000

    @pytest.mark.asyncio
    async def test_remember_requires_project_id(self):
        result = await remember_execute({
            "memory": "Some project fact",
            "scope": "project",
        })
        assert "error" in result
        assert "project_id" in result["error"].lower()

    @pytest.mark.asyncio
    @patch("src.db.save_memory")
    async def test_remember_importance_default(self, mock_save):
        mock_save.return_value = {"id": "def-123"}

        await remember_execute({"memory": "A fact", "scope": "global"})

        call_args = mock_save.call_args
        assert call_args.kwargs["importance"] == 5


# ---------------------------------------------------------------------------
# recall tool
# ---------------------------------------------------------------------------

class TestRecallDefinition:
    def test_name(self):
        assert RECALL_DEF["name"] == "recall"

    def test_no_required_fields(self):
        # recall has no required fields — all filters are optional
        assert "required" not in RECALL_DEF["input_schema"]


class TestRecallExecute:
    @pytest.mark.asyncio
    @patch("src.db.search_memories")
    async def test_recall_returns_memories(self, mock_search):
        mock_search.return_value = [
            {"id": "m1", "memory": "Blattner does TX solar", "scope": "global", "importance": 8},
            {"id": "m2", "memory": "McCarthy active in IL", "scope": "global", "importance": 6},
        ]

        result = await recall_execute({"keyword": "solar", "scope": "global"})

        mock_search.assert_called_once_with(
            keyword="solar",
            scope="global",
            project_id=None,
            limit=10,
        )
        assert result["count"] == 2
        assert len(result["memories"]) == 2
        assert result["memories"][0]["id"] == "m1"

    @pytest.mark.asyncio
    @patch("src.db.search_memories")
    async def test_recall_empty_result(self, mock_search):
        mock_search.return_value = []

        result = await recall_execute({"keyword": "nonexistent"})

        assert result == {"memories": [], "count": 0}

    @pytest.mark.asyncio
    @patch("src.db.search_memories")
    async def test_recall_with_project_id(self, mock_search):
        mock_search.return_value = []

        await recall_execute({"project_id": "proj-uuid-123", "limit": 5})

        mock_search.assert_called_once_with(
            keyword=None,
            scope=None,
            project_id="proj-uuid-123",
            limit=5,
        )


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------

class TestRegistryIntegration:
    def test_tools_registered(self):
        from src.tools import get_tool_names
        names = get_tool_names()
        assert "remember" in names
        assert "recall" in names
