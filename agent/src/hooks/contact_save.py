"""ContactSaveHook — updates entity discovery status when contacts are saved.

Will be wired into the AgentRuntime hook system once the runtime revamp lands.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ContactSaveHook:
    """Post-tool hook for save_contact."""

    async def pre_tool(self, tool_name: str, tool_input: dict, context: dict) -> dict:
        """No-op pre-tool. Returns input unchanged."""
        return {"action": "continue", "tool_input": tool_input}

    async def post_tool(
        self, tool_name: str, tool_input: dict, result: dict, context: dict
    ) -> dict:
        """After save_contact succeeds, update entity discovery status."""
        if tool_name != "save_contact":
            return result
        if not isinstance(result, dict) or result.get("status") != "success":
            return result

        entity_id = tool_input.get("entity_id")
        if entity_id:
            try:
                from ..db import get_client
                get_client().table("entities").update({
                    "contact_discovery_status": "in_progress"
                }).eq("id", entity_id).execute()
            except Exception:
                logger.warning("Failed to update entity contact_discovery_status", exc_info=True)

        return result
