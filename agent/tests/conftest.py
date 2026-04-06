"""Shared test fixtures for EPC discovery agent tests."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

# Set required env vars before any src imports
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key")
os.environ.setdefault("TAVILY_API_KEY", "tvly-test-key")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")


@pytest.fixture()
def sample_project() -> dict:
    return {
        "id": "proj-001",
        "queue_id": "Q-100",
        "iso_region": "ERCOT",
        "project_name": "Sunrise Solar",
        "developer": "SunDev LLC",
        "epc_company": None,
        "state": "TX",
        "county": "Travis",
        "latitude": 30.27,
        "longitude": -97.74,
        "mw_capacity": 250,
        "fuel_type": "Solar",
        "queue_date": "2024-06-15",
        "expected_cod": "2026-12-01",
        "status": "Active",
        "source": "ercot",
        "lead_score": 85,
        "raw_data": None,
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
    }


@pytest.fixture()
def sample_project_b() -> dict:
    return {
        "id": "proj-002",
        "queue_id": "Q-200",
        "iso_region": "CAISO",
        "project_name": "Desert Wind",
        "developer": "WindCo Inc",
        "epc_company": None,
        "state": "CA",
        "county": "Kern",
        "latitude": 35.37,
        "longitude": -118.97,
        "mw_capacity": 100,
        "fuel_type": "Solar",
        "queue_date": "2024-08-01",
        "expected_cod": "2026-06-01",
        "status": "Active",
        "source": "caiso",
        "lead_score": 70,
        "raw_data": None,
        "created_at": "2025-02-01T00:00:00Z",
        "updated_at": "2025-02-01T00:00:00Z",
    }


@pytest.fixture()
def sample_discovery() -> dict:
    return {
        "id": "disc-001",
        "project_id": "proj-001",
        "epc_contractor": "McCarthy Building",
        "confidence": "likely",
        "sources": [
            {
                "channel": "trade_publication",
                "publication": "Solar Power World",
                "date": "2025-03-15",
                "url": "https://example.com/article",
                "excerpt": "McCarthy Building awarded EPC contract for Sunrise Solar",
                "reliability": "high",
            }
        ],
        "reasoning": "Found trade publication evidence.",
        "related_leads": [],
        "review_status": "pending",
        "agent_log": [{"iteration": 0, "stop_reason": "tool_use"}],
        "tokens_used": 5000,
        "created_at": "2025-03-01T00:00:00Z",
        "updated_at": "2025-03-01T00:00:00Z",
    }


def make_agent_result(**overrides):
    """Build an AgentResult with sensible defaults."""
    from src.models import AgentResult, EpcSource

    defaults = {
        "epc_contractor": "McCarthy Building",
        "confidence": "likely",
        "sources": [
            EpcSource(
                channel="trade_publication",
                publication="Solar Power World",
                excerpt="McCarthy awarded contract",
                reliability="high",
            )
        ],
        "reasoning": "Found in trade publication.",
        "related_leads": [],
        "searches_performed": ["SunDev Sunrise Solar EPC"],
    }
    defaults.update(overrides)
    return AgentResult(**defaults)


def make_claude_response(
    *, stop_reason="end_turn", content=None, input_tokens=100, output_tokens=50
):
    """Build a mock Anthropic Messages response."""
    resp = MagicMock()
    resp.stop_reason = stop_reason
    resp.content = content or []
    resp.usage = MagicMock()
    resp.usage.input_tokens = input_tokens
    resp.usage.output_tokens = output_tokens
    return resp


def make_tool_use_block(*, name, input_data, block_id="tool-1"):
    """Build a mock tool_use content block."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.input = input_data
    block.id = block_id
    return block


def make_text_block(text):
    """Build a mock text content block."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block
