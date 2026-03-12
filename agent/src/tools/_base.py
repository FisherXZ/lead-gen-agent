"""Shared types and helpers for tool modules."""

from __future__ import annotations

import uuid
from typing import TypedDict


class ToolDef(TypedDict):
    """Standard tool definition for the Claude API."""

    name: str
    description: str
    input_schema: dict


def validate_uuid(value: str) -> bool:
    """Check if a string is a valid UUID."""
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False
