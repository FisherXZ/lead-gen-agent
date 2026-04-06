"""Accept or reject a pending EPC discovery.

Called by the chat agent after the user reviews a finding via
request_discovery_review and decides to accept or reject it.
"""

from __future__ import annotations

import logging

from .. import db
from ..knowledge_base import process_rejection_into_kb, promote_discovery_to_kb
from ..models import AgentResult, EpcSource

logger = logging.getLogger(__name__)

DEFINITION = {
    "name": "approve_discovery",
    "description": (
        "Accept or reject a pending EPC discovery after human review. "
        "Use action='accepted' when the user approves the finding. "
        "Use action='rejected' with a reason when the user rejects it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "discovery_id": {
                "type": "string",
                "description": "The discovery ID to act on.",
            },
            "action": {
                "type": "string",
                "enum": ["accepted", "rejected"],
                "description": "Whether to accept or reject the discovery.",
            },
            "reason": {
                "type": "string",
                "description": (
                    "Why the discovery is being accepted or rejected. Required for rejections."
                ),
            },
        },
        "required": ["discovery_id", "action"],
    },
}


async def execute(tool_input: dict) -> dict:
    discovery_id = tool_input.get("discovery_id")
    action = tool_input.get("action")
    reason = tool_input.get("reason")

    if not discovery_id:
        return {"error": "discovery_id is required"}
    if action not in ("accepted", "rejected"):
        return {"error": "action must be 'accepted' or 'rejected'"}

    # Look up the discovery
    client = db.get_client()
    resp = client.table("epc_discoveries").select("*").eq("id", discovery_id).execute()
    if not resp.data:
        return {"error": f"Discovery {discovery_id} not found"}

    discovery = resp.data[0]

    if discovery["review_status"] != "pending":
        return {
            "error": f"Discovery is already {discovery['review_status']}",
            "review_status": discovery["review_status"],
        }

    if action == "accepted":
        db.update_discovery(discovery_id, {"review_status": "accepted"})
        db.update_project_epc(discovery["project_id"], discovery["epc_contractor"])

        # Promote to knowledge base
        project = db.get_project(discovery["project_id"])
        if project:
            try:
                sources = [EpcSource(**s) for s in (discovery.get("sources") or [])]
                result = AgentResult(
                    epc_contractor=discovery.get("epc_contractor"),
                    confidence=discovery.get("confidence", "unknown"),
                    sources=sources,
                    reasoning=discovery.get("reasoning", ""),
                    related_leads=discovery.get("related_leads", []),
                    searches_performed=discovery.get("searches_performed", []),
                )
                promote_discovery_to_kb(discovery["project_id"], result, project)
            except Exception:
                logger.warning("KB promotion failed for discovery %s", discovery_id, exc_info=True)

        return {
            "status": "accepted",
            "discovery_id": discovery_id,
            "epc_contractor": discovery["epc_contractor"],
            "message": f"Discovery accepted: {discovery['epc_contractor']} for project.",
        }

    else:
        # Rejected
        update_data: dict = {"review_status": "rejected"}
        if reason:
            update_data["rejection_reason"] = reason
        db.update_discovery(discovery_id, update_data)

        try:
            process_rejection_into_kb(discovery, reason)
        except Exception:
            logger.warning(
                "KB rejection processing failed for discovery %s",
                discovery_id,
                exc_info=True,
            )

        return {
            "status": "rejected",
            "discovery_id": discovery_id,
            "reason": reason or "No reason provided",
            "message": "Discovery rejected." + (f" Reason: {reason}" if reason else ""),
        }
