"""Pydantic models for API request/response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class DiscoverRequest(BaseModel):
    project_id: str
    plan: str | None = None  # Approved research plan from /api/discover/plan


class DiscoverPlanRequest(BaseModel):
    project_id: str


class ContactDiscoverRequest(BaseModel):
    entity_id: str


class HubSpotConnectRequest(BaseModel):
    token: str
    pipeline_id: str | None = None
    deal_stage_id: str | None = None


class HubSpotPushRequest(BaseModel):
    project_id: str


class BatchDiscoverRequest(BaseModel):
    project_ids: list[str]


class ReviewRequest(BaseModel):
    action: str  # "accepted" or "rejected"
    reason: str | None = None


class EpcSource(BaseModel):
    channel: str
    publication: str | None = None
    date: str | None = None
    url: str | None = None
    excerpt: str
    reliability: str = "medium"  # high / medium / low
    search_query: str | None = None
    source_method: str | None = None


class NegativeEvidence(BaseModel):
    search_query: str
    expected_to_find: str | None = None
    what_was_found: str  # "nothing", "contradictory", "different_epc", "different_project"


class ResearchError(BaseModel):
    # "api_key_missing" | "anthropic_error" | "search_tool_error"
    # | "max_iterations" | "no_report" | "db_error" | "unknown"
    category: str
    message: str  # human-readable description
    detail: str | None = None


class TriageResult(BaseModel):
    action: Literal["research", "skip"] = "research"
    corrected_project: dict | None = None  # project dict with resolved name/developer
    skip_reason: str | None = None  # machine-readable code
    triage_log: list[dict] = []  # rules fired, tools called, findings
    tokens_used: int = 0


class AgentResult(BaseModel):
    epc_contractor: str | None = None
    confidence: str = "unknown"  # confirmed / likely / possible / unknown
    agent_confidence: str | None = None  # raw agent-reported confidence before upgrade
    source_count: int = 0  # number of independent sources
    confidence_warning: str | None = None  # e.g. "Unverified — single low-reliability source"
    sources: list[EpcSource] = []
    reasoning: str | dict = ""
    related_leads: list[dict] = []
    searches_performed: list[str] = []
    negative_evidence: list[NegativeEvidence] = []
    error: ResearchError | None = None


class ChatMessagePart(BaseModel):
    type: str  # "text", "file"
    text: str | None = None
    # File attachment fields (type="file") — AI SDK FileUIPart format
    mediaType: str | None = None  # MIME type: "application/pdf", "image/png", etc.
    filename: str | None = None
    url: str | None = None  # data URL: "data:<mediaType>;base64,<data>"


# Supported file types and their Claude API content block mappings
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
_DOCUMENT_TYPES = {"application/pdf"}
_TEXT_FILE_TYPES = {"text/plain", "text/csv", "text/markdown"}


class ChatMessage(BaseModel):
    role: str
    content: str | None = None  # v3 SDK sends content
    parts: list[ChatMessagePart] | None = None  # v6 SDK sends parts

    def get_text(self) -> str:
        """Extract text content from either format."""
        if self.content:
            return self.content
        if self.parts:
            return " ".join(p.text for p in self.parts if p.type == "text" and p.text)
        return ""

    def get_content_blocks(self) -> str | list[dict]:
        """Build Claude API content blocks, handling text + files.

        Returns a plain string for text-only messages (backwards compatible),
        or a list of content blocks when files are present.
        """
        if self.content and not self.parts:
            return self.content

        if not self.parts:
            return ""

        has_files = any(p.type == "file" and p.url for p in self.parts)
        if not has_files:
            return self.get_text()

        blocks: list[dict] = []
        for p in self.parts:
            if p.type == "text" and p.text:
                blocks.append({"type": "text", "text": p.text})
            elif p.type == "file" and p.url:
                media_type = p.mediaType or ""
                # Extract base64 data from data URL
                b64_data = _extract_base64(p.url)
                if not b64_data:
                    continue

                if media_type in _IMAGE_TYPES:
                    blocks.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64_data,
                            },
                        }
                    )
                elif media_type in _DOCUMENT_TYPES:
                    blocks.append(
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64_data,
                            },
                        }
                    )
                elif media_type in _TEXT_FILE_TYPES:
                    import base64

                    try:
                        text_content = base64.b64decode(b64_data).decode("utf-8")
                        label = p.filename or "file"
                        blocks.append(
                            {
                                "type": "text",
                                "text": f"[File: {label}]\n{text_content}",
                            }
                        )
                    except Exception:
                        blocks.append(
                            {
                                "type": "text",
                                "text": f"[Could not decode file: {p.filename}]",
                            }
                        )

        return blocks if blocks else ""


def _extract_base64(data_url: str) -> str | None:
    """Extract base64 data from a data URL like 'data:image/png;base64,iVBOR...'."""
    if not data_url:
        return None
    if data_url.startswith("data:"):
        parts = data_url.split(",", 1)
        return parts[1] if len(parts) == 2 else None
    # Already raw base64
    return data_url


class ChatRequest(BaseModel):
    id: str | None = None  # chat ID from AI SDK
    messages: list[ChatMessage]
    conversation_id: str | None = None  # None = new conversation


class EpcDiscoveryResponse(BaseModel):
    id: str
    project_id: str
    epc_contractor: str
    confidence: str
    sources: list[dict]
    reasoning: str | dict | None
    related_leads: list[dict]
    review_status: str
    tokens_used: int
    created_at: str
    updated_at: str
