"""Tests for the think tool."""

import pytest

from src.tools.think import execute


@pytest.mark.asyncio
async def test_think_returns_recorded():
    result = await execute({"thought": "Weighing two conflicting sources..."})
    assert result["recorded"] is True
    assert "thought" not in result  # Don't echo back to save tokens


@pytest.mark.asyncio
async def test_think_empty_thought():
    result = await execute({"thought": ""})
    assert result["recorded"] is True
