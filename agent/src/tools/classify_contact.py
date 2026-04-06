"""Classify a contact against the 'solar EPC robot buyer' persona.

Uses Claude Haiku with tool_use structured output to score four boolean criteria,
then writes results to the contact_persona_scores table.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from ..db import get_anthropic_client, get_client
from ._base import validate_uuid

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic input
# ---------------------------------------------------------------------------


class Input(BaseModel):
    contact_id: str = Field(..., description="Contact UUID to classify")


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------


DEFINITION = {
    "name": "classify_contact",
    "description": (
        "Score a contact against the 'solar EPC robot buyer' persona using AI. "
        "Evaluates role alignment, decision-making authority, project relevance, "
        "and overall persona fit. Writes results to contact_persona_scores. "
        "Use after finding contacts to identify the best outreach targets."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "contact_id": {
                "type": "string",
                "description": "Contact UUID to classify (from contacts table).",
            },
        },
        "required": ["contact_id"],
    },
}


# ---------------------------------------------------------------------------
# Scoring tool schema passed to Claude
# ---------------------------------------------------------------------------

_SCORE_TOOL = {
    "name": "score_contact",
    "description": "Score a contact against the buyer persona",
    "input_schema": {
        "type": "object",
        "properties": {
            "role_aligned": {"type": "boolean"},
            "is_decision_maker": {"type": "boolean"},
            "project_relevant": {"type": "boolean"},
            "persona_fit": {"type": "boolean"},
            "reasoning": {
                "type": "object",
                "properties": {
                    "role_reasoning": {"type": "string"},
                    "decision_maker_reasoning": {"type": "string"},
                    "project_reasoning": {"type": "string"},
                    "persona_reasoning": {"type": "string"},
                },
                "required": [
                    "role_reasoning",
                    "decision_maker_reasoning",
                    "project_reasoning",
                    "persona_reasoning",
                ],
            },
        },
        "required": [
            "role_aligned",
            "is_decision_maker",
            "project_relevant",
            "persona_fit",
            "reasoning",
        ],
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_prompt(contact: dict, entity_name: str) -> str:
    full_name = contact.get("full_name") or "Unknown"
    title = contact.get("title") or "Unknown title"
    headline = contact.get("linkedin_headline") or ""
    experience = contact.get("linkedin_experience") or []

    # Summarise experience — up to 3 most recent roles
    if isinstance(experience, list) and experience:
        exp_lines = []
        for role in experience[:3]:
            if isinstance(role, dict):
                role_title = role.get("title", "")
                company = role.get("company", "")
                if role_title or company:
                    exp_lines.append(f"  - {role_title} at {company}".strip(" at"))
        experience_summary = "\n".join(exp_lines) if exp_lines else "No experience listed"
    else:
        experience_summary = "No experience listed"

    return f"""Classify this contact for Civ Robotics, which sells \
autonomous layout robots to solar EPCs.

Contact: {full_name}, {title} at {entity_name}
LinkedIn headline: {headline}
Experience:
{experience_summary}

Score each criterion:
- role_aligned: Is this a construction/operations/PM/procurement role? \
(NOT HR/Finance/Legal/Marketing/IT)
- is_decision_maker: VP/Director/Senior level who could approve \
equipment purchases?
- project_relevant: Working in solar energy, renewable construction, \
or the specific region?
- persona_fit: Overall — would this person be interested in robots \
that automate layout staking on solar farms?

Be strict: only mark true if genuinely aligned. Use the score_contact tool to return results."""


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------


async def execute(tool_input: dict) -> dict:
    contact_id = tool_input.get("contact_id", "").strip()

    if not validate_uuid(contact_id):
        return {
            "status": "error",
            "error": f"Invalid contact_id: {contact_id!r}",
            "error_category": "validation_error",
        }

    client = get_client()

    # 1. Fetch contact
    contact_resp = (
        client.table("contacts")
        .select(
            "id, entity_id, full_name, title, linkedin_headline, linkedin_experience, source_method"
        )
        .eq("id", contact_id)
        .limit(1)
        .execute()
    )
    if not contact_resp.data:
        return {
            "status": "error",
            "error": f"Contact not found: {contact_id}",
            "error_category": "not_found",
        }

    contact = contact_resp.data[0]
    entity_id = contact.get("entity_id")

    # 2. Fetch associated entity name
    entity_name = "Unknown Company"
    if entity_id:
        entity_resp = (
            client.table("entities").select("id, name").eq("id", entity_id).limit(1).execute()
        )
        if entity_resp.data:
            entity_name = entity_resp.data[0].get("name") or entity_name

    # 3. Call Claude Haiku for structured scoring
    prompt = _build_prompt(contact, entity_name)

    anthropic_client = get_anthropic_client()
    response = await anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
        tools=[_SCORE_TOOL],
        tool_choice={"type": "tool", "name": "score_contact"},
    )

    # Extract tool_use block
    scores = None
    for block in response.content:
        if (
            getattr(block, "type", None) == "tool_use"
            and getattr(block, "name", None) == "score_contact"
        ):
            scores = block.input
            break

    if scores is None:
        return {"error": "Claude did not return a score_contact tool call"}

    role_aligned = bool(scores.get("role_aligned"))
    is_decision_maker = bool(scores.get("is_decision_maker"))
    project_relevant = bool(scores.get("project_relevant"))
    persona_fit = bool(scores.get("persona_fit"))
    reasoning = scores.get("reasoning", {})

    # Compute match_score and is_match locally (mirrors the generated columns)
    true_count = sum([role_aligned, is_decision_maker, project_relevant, persona_fit])
    match_score = round(true_count * 0.25, 2)
    is_match = true_count == 4

    # 4. Upsert to contact_persona_scores
    upsert_data = {
        "contact_id": contact_id,
        "ai_role_aligned": role_aligned,
        "ai_is_decision_maker": is_decision_maker,
        "ai_project_relevant": project_relevant,
        "ai_persona_fit": persona_fit,
        "ai_reasoning": reasoning,
        "ai_classified_at": datetime.now(UTC).isoformat(),
    }
    try:
        client.table("contact_persona_scores").upsert(
            upsert_data, on_conflict="contact_id"
        ).execute()
    except Exception as exc:
        logger.warning("Failed to write persona score for %s: %s", contact_id, exc)

    return {
        "status": "success",
        "data": {
            "contact_id": contact_id,
            "role_aligned": role_aligned,
            "is_decision_maker": is_decision_maker,
            "project_relevant": project_relevant,
            "persona_fit": persona_fit,
            "match_score": match_score,
            "is_match": is_match,
            "reasoning": reasoning,
        },
        "source": "classification",
    }
