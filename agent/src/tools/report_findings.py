"""Report structured EPC discovery findings."""

from __future__ import annotations

DEFINITION = {
    "name": "report_findings",
    "description": (
        "Report your EPC discovery findings as a structured result. Call this "
        "EXACTLY ONCE when you are done researching a project's EPC contractor. "
        "You MUST call this even if you found nothing — set confidence to 'unknown'. "
        "Before calling with confidence 'likely' or 'possible', verify the candidate: "
        "check that they operate at the right scale (utility-scale solar, 50MW+), "
        "confirm the source is about this specific project (not a similarly-named one), "
        "and search for counter-evidence. Reporting 'unknown' after thorough research "
        "is better than reporting an unverified guess."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "epc_contractor": {
                "type": ["string", "null"],
                "description": "Name of the EPC contractor, or null if not found.",
            },
            "confidence": {
                "type": "string",
                "enum": ["confirmed", "likely", "possible", "unknown"],
                "description": (
                    "Confidence level. "
                    "'confirmed': 2+ independent sources, at least one first-party. "
                    "'likely': 1 reliable source that specifically names the EPC "
                    "for this project, AND the EPC operates at this scale. "
                    "'possible': Indirect evidence only "
                    "(e.g., same developer used this EPC elsewhere). "
                    "'unknown': No project-specific evidence found."
                ),
            },
            "sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "channel": {
                            "type": "string",
                            "description": (
                                "Source type: 'press_release', 'epc_portfolio', "
                                "'regulatory_filing', 'trade_publication', "
                                "'sec_filing', 'news', 'secondary'."
                            ),
                        },
                        "publication": {
                            "type": ["string", "null"],
                            "description": (
                                "Publication name (e.g. 'Solar Power World', "
                                "'McCarthy Building Companies')."
                            ),
                        },
                        "date": {
                            "type": "string",
                            "description": (
                                "Publication or access date (YYYY-MM-DD, YYYY-MM, or YYYY). "
                                "REQUIRED — use the article publication date, or today's date "
                                "if accessing a live website/portfolio page with no date."
                            ),
                        },
                        "url": {
                            "type": "string",
                            "description": (
                                "Source URL (REQUIRED). Use the actual URL from the search "
                                "result or fetched page. If no direct URL exists, use a "
                                "'search:' prefix followed by the query that found this info "
                                "(e.g., 'search:NextEra Blattner solar EPC')."
                            ),
                        },
                        "excerpt": {
                            "type": "string",
                            "description": "Key quote or excerpt that supports the finding.",
                        },
                        "reliability": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                            "description": (
                                "Source reliability. 'high': first-party (developer PR, "
                                "EPC website, regulatory filing). 'medium': trade publication, "
                                "SEC filing. 'low': general news, secondary aggregator, LinkedIn."
                            ),
                        },
                        "source_method": {
                            "type": "string",
                            "enum": [
                                "brave_search",
                                "tavily_search",
                                "page_fetch",
                                "iso_filing",
                                "knowledge_base",
                            ],
                            "description": (
                                "How this source was discovered. "
                                "'brave_search': Found via Brave web search "
                                "(web_search_broad tool). "
                                "'tavily_search': Found via Tavily deep search "
                                "(web_search tool). "
                                "'page_fetch': Found by directly fetching and "
                                "reading a web page. "
                                "'iso_filing': Extracted from ISO interconnection "
                                "queue filing data. "
                                "'knowledge_base': Retrieved from the internal "
                                "knowledge base of prior research."
                            ),
                        },
                    },
                    "required": ["channel", "excerpt", "url", "source_method", "date"],
                },
                "description": (
                    "All sources found during research, including those that didn't lead anywhere."
                ),
            },
            "reasoning": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": (
                            "1-2 sentence conclusion. Reference sources with [N] "
                            "(1-indexed, matching position in sources array). "
                            "For 'unknown': explain why no EPC was found."
                        ),
                    },
                    "supporting_evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Key evidence points, strongest first. Each should cite "
                            "a source with [N] where applicable. Include verification "
                            "checks performed (scale, specificity, counter-evidence)."
                        ),
                    },
                    "gaps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "What's missing, uncertain, or couldn't be verified. "
                            "For 'unknown' results this should be substantial — "
                            "explain why the EPC isn't public yet."
                        ),
                    },
                },
                "required": ["summary", "supporting_evidence", "gaps"],
            },
            "searches_performed": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Every search query executed during research, including "
                    "dead ends. This helps avoid duplicate work on re-research."
                ),
            },
            "negative_evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "search_query": {
                            "type": "string",
                            "description": "The search query that was executed.",
                        },
                        "expected_to_find": {
                            "type": "string",
                            "description": "What you expected to find with this search.",
                        },
                        "what_was_found": {
                            "type": "string",
                            "enum": [
                                "nothing",
                                "contradictory",
                                "different_epc",
                                "different_project",
                            ],
                            "description": (
                                "What was actually found. "
                                "'nothing': No relevant results. "
                                "'contradictory': Found info that contradicts the candidate EPC. "
                                "'different_epc': Found a different EPC named for this project. "
                                "'different_project': Results were about a different project."
                            ),
                        },
                    },
                    "required": ["search_query", "what_was_found"],
                },
                "description": (
                    "Searches that found nothing or contradictory information. "
                    "Helps calibrate confidence and avoid repeating dead-end searches."
                ),
            },
            "related_findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "developer": {"type": "string"},
                        "epc_contractor": {"type": "string"},
                        "confidence": {
                            "type": "string",
                            "enum": ["confirmed", "likely", "possible"],
                        },
                        "state": {"type": ["string", "null"]},
                        "excerpt": {"type": "string"},
                    },
                    "required": ["developer", "epc_contractor", "confidence"],
                },
                "description": (
                    "Other developer→EPC relationships discovered incidentally "
                    "during research. These get stored in the knowledge base "
                    "for future use."
                ),
            },
        },
        "required": ["confidence", "reasoning", "searches_performed"],
    },
}


async def execute(tool_input: dict) -> dict:
    """Acknowledge findings. Parsing into AgentResult happens in the caller."""
    # This tool's output isn't used directly — the caller (research.py or chat_agent.py)
    # reads the tool_input to construct the AgentResult. We just acknowledge receipt.
    return {"status": "recorded"}
