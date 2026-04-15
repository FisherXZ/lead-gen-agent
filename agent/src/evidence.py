"""Structured evidence store for the research loop.

Accumulates findings in a typed list, deduplicates by URL,
and formats evidence for reflection and synthesis prompts.
"""

from __future__ import annotations

import asyncio

from .models import Finding


class EvidenceStore:
    """Accumulates research findings across iterations.

    Supports single-project (synchronous `add`) and concurrent batch
    (async `add_async`, lock-guarded) usage patterns.
    """

    def __init__(self) -> None:
        self.findings: list[Finding] = []
        self.visited_urls: set[str] = set()
        self.searches_performed: list[str] = []
        self._lock: asyncio.Lock | None = None

    def _ensure_lock(self) -> asyncio.Lock:
        """Lazily construct the lock so instances can be created outside an event loop."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def add(self, finding: Finding) -> bool:
        """Add a finding. Returns False if URL already seen (dedup).

        Not thread-safe. Use `add_async` when multiple coroutines share one store.
        """
        if finding.source_url in self.visited_urls:
            return False
        self.findings.append(finding)
        self.visited_urls.add(finding.source_url)
        return True

    async def add_async(self, finding: Finding) -> bool:
        """Thread-safe add for concurrent batch research."""
        async with self._ensure_lock():
            return self.add(finding)

    def record_search(self, query: str) -> None:
        """Record a search query that was executed."""
        self.searches_performed.append(query)

    def format_for_prompt(self) -> str:
        """Format all findings as numbered evidence for an LLM prompt."""
        if not self.findings:
            return "No findings collected yet."

        lines = []
        for i, f in enumerate(self.findings, 1):
            lines.append(
                f"[{i}] ({f.reliability}, {f.source_tool}) {f.text}\n"
                f"    Source: {f.source_url}"
            )
        return "\n".join(lines)


def extract_findings_from_tool_result(
    tool_name: str,
    tool_input: dict,
    result: dict,
    evidence: EvidenceStore,
    iteration: int = 0,
) -> None:
    """Extract findings from a tool result into the evidence store.

    Maps tool-specific result shapes to Finding objects. Skips errors
    and results with insufficient content.

    Tool result shapes (verified from actual tool code):
    - web_search/web_search_broad: {"results": [{"title", "url", "content", "score"}]}
    - fetch_page: {"url", "text", "length"}
    - search_sec_edgar: {"results": [{"company_name", "form_type", "filing_date", "url", ...}]}
    - search_osha: {"results": [{"employer_name", "address", "inspection_date", "detail_url", ...}]}
    - search_wiki_solar: {"found": bool, "epc_name", "wiki_solar_rank", "mw_installed", ...}
    - search_spw: {"found": bool, "epc_name", "spw_rank", "spw_service_type", ...}
    - search_enr: {"results": [...]} or {"found": bool, ...}
    """
    if "error" in result:
        return

    # Record the search query if present
    query = (
        tool_input.get("query", "")
        or tool_input.get("employer_name", "")
        or tool_input.get("company_name", "")
        or tool_input.get("epc_name", "")
    )
    if query:
        evidence.record_search(query)

    if tool_name in ("web_search", "web_search_broad"):
        source_tool = "tavily_search" if tool_name == "web_search" else "brave_search"
        for item in result.get("results", []):
            content = item.get("content", "")
            url = item.get("url", "")
            title = item.get("title", "")
            if content and url and len(content) >= 50:
                evidence.add(Finding(
                    text=f"{title}: {content}" if title else content,
                    source_url=url,
                    source_tool=source_tool,
                    reliability="medium",
                    iteration=iteration,
                ))

    elif tool_name == "fetch_page":
        url = tool_input.get("url", "")
        text = result.get("text", "")
        if text and url and len(text) >= 100:
            evidence.add(Finding(
                text=text[:2000],
                source_url=url,
                source_tool="page_fetch",
                reliability="medium",
                iteration=iteration,
            ))

    elif tool_name == "search_sec_edgar":
        for filing in result.get("results", []):
            url = filing.get("url", "")
            form_type = filing.get("form_type", "")
            company = filing.get("company_name", "")
            date = filing.get("filing_date", "")
            desc = filing.get("description", "")
            if url:
                evidence.add(Finding(
                    text=f"SEC {form_type} ({date}): {company} — {desc}".strip(" —"),
                    source_url=url,
                    source_tool="sec_edgar",
                    reliability="high",
                    iteration=iteration,
                ))

    elif tool_name == "search_osha":
        for record in result.get("results", []):
            employer = record.get("employer_name", "")
            address = record.get("address", "")
            date = record.get("inspection_date", "")
            url = record.get("detail_url", "")
            if employer and url:
                evidence.add(Finding(
                    text=f"OSHA inspection: {employer} at {address} ({date})",
                    source_url=url,
                    source_tool="osha_inspection",
                    reliability="high",
                    iteration=iteration,
                ))

    elif tool_name == "search_wiki_solar":
        if result.get("found") and result.get("wiki_solar_rank") is not None:
            name = result.get("epc_name", "")
            rank = result.get("wiki_solar_rank")
            mw = result.get("mw_installed", "?")
            evidence.add(Finding(
                text=f"Wiki-Solar ranking: {name} ranked #{rank}, {mw}MW installed",
                source_url=f"ranking:wiki_solar:{name}",
                source_tool="wiki_solar_ranking",
                reliability="medium",
                iteration=iteration,
            ))

    elif tool_name == "search_spw":
        if result.get("found") and result.get("spw_rank") is not None:
            name = result.get("epc_name", "")
            rank = result.get("spw_rank")
            svc = result.get("spw_service_type", "")
            evidence.add(Finding(
                text=f"SPW ranking: {name} ranked #{rank}, service type: {svc}",
                source_url=f"ranking:spw:{name}",
                source_tool="spw_ranking",
                reliability="medium",
                iteration=iteration,
            ))

    elif tool_name == "search_enr":
        for entry in result.get("results", []):
            name = entry.get("name", "") or entry.get("company", "")
            if name:
                evidence.add(Finding(
                    text=f"ENR ranking: {name}",
                    source_url=f"ranking:enr:{name}",
                    source_tool="enr_ranking",
                    reliability="medium",
                    iteration=iteration,
                ))
