"""Tests for Pydantic input validation hook in execute_tool().

TDD: these tests were written BEFORE the implementation.

Coverage:
  1. Tool WITH Input model + invalid input → returns validation_error dict
  2. Tool WITH Input model + valid input → executes successfully, defaults applied
  3. Tool WITHOUT Input model → unaffected (backwards compatibility)
"""

from __future__ import annotations

import types

import pytest
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Helpers: build minimal fake tool modules without touching the real registry
# ---------------------------------------------------------------------------


def _make_tool_with_input(schema: type[BaseModel], execute_result: dict) -> types.ModuleType:
    """Return a mock module that has both an Input model and an execute coroutine."""
    mod = types.ModuleType("_fake_tool_with_input")
    mod.DEFINITION = {"name": "_fake_tool_with_input"}
    mod.Input = schema

    async def execute(tool_input: dict) -> dict:  # pragma: no cover
        return {"ok": True, "received": tool_input, **execute_result}

    mod.execute = execute
    return mod


def _make_tool_without_input(execute_result: dict) -> types.ModuleType:
    """Return a mock module with NO Input model — legacy / plain tool."""
    mod = types.ModuleType("_fake_tool_plain")
    mod.DEFINITION = {"name": "_fake_tool_plain"}

    async def execute(tool_input: dict) -> dict:  # pragma: no cover
        return {"ok": True, **execute_result}

    mod.execute = execute
    return mod


# ---------------------------------------------------------------------------
# Fixtures: inject mock modules into the registry for each test
# ---------------------------------------------------------------------------


@pytest.fixture()
def patched_registry(monkeypatch):
    """Patch _REGISTRY in src.tools and return it for manipulation."""
    import src.tools as tools_mod

    class Schema(BaseModel):
        query: str
        limit: int = 10  # has a default

    tool_with_input = _make_tool_with_input(Schema, {})
    tool_without_input = _make_tool_without_input({})

    fake_registry = {
        "_fake_tool_with_input": tool_with_input,
        "_fake_tool_plain": tool_without_input,
    }
    monkeypatch.setattr(tools_mod, "_REGISTRY", fake_registry)
    return fake_registry


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_input_returns_validation_error(patched_registry):
    """Calling execute_tool with wrong types should return a validation_error dict."""
    from src.tools import execute_tool

    result = await execute_tool("_fake_tool_with_input", {"query": 123, "limit": "not-a-number"})

    # Should NOT raise — should return a structured error
    assert isinstance(result, dict)
    assert result.get("error_category") == "validation_error"
    assert "Invalid input" in result.get("error", "")


@pytest.mark.asyncio
async def test_missing_required_field_returns_validation_error(patched_registry):
    """Omitting a required field (query) should yield a validation_error."""
    from src.tools import execute_tool

    result = await execute_tool("_fake_tool_with_input", {})  # query is required

    assert isinstance(result, dict)
    assert result.get("error_category") == "validation_error"


@pytest.mark.asyncio
async def test_valid_input_executes_with_defaults_applied(patched_registry):
    """Valid input passes through; Pydantic-applied defaults land in execute()."""
    from src.tools import execute_tool

    # Provide only the required field; expect `limit` default (10) to be injected
    result = await execute_tool("_fake_tool_with_input", {"query": "solar EPC"})

    assert result.get("ok") is True
    # execute() received model_dump() — defaults should be present
    received = result.get("received", {})
    assert received.get("query") == "solar EPC"
    assert received.get("limit") == 10  # default was applied by Pydantic


@pytest.mark.asyncio
async def test_tool_without_input_model_unaffected(patched_registry):
    """Tools that don't define an Input class must still work as before."""
    from src.tools import execute_tool

    result = await execute_tool("_fake_tool_plain", {"anything": "goes"})

    assert result.get("ok") is True
    # No validation_error
    assert "error_category" not in result
