# TODO

## Agent Transparency v2 — Infrastructure-Level Progress

**Context:** v1 uses `notify_progress` as an LLM-called tool. This works but has limitations: the LLM sometimes forgets to call it, stage names aren't consistent, and each call costs tokens + latency. v2 moves progress reporting to the infrastructure layer.

**Why:** PostHog learned the same lesson — moved from "LLM calls tools in a loop" to graph-style workflows. AG-UI Protocol and Chainlit both emit progress from the framework, not the LLM.

### Changes

- [ ] **Auto-emit `round-start` SSE events** — the `for _round in range(MAX_TOOL_ROUNDS)` loop in `chat_agent.py` already knows when a new round begins. Emit a framework-level event instead of relying on the LLM to call `notify_progress`.
- [ ] **Infer stages from tool types** — `web_search` → "Searching", `fetch_page` → "Reading", `query_knowledge_base` → "Cross-referencing", `report_findings` → "Compiling". Infrastructure labels stages automatically, no LLM involvement.
- [ ] **Deprecate `notify_progress` tool** — remove it from the tool registry once infrastructure-level progress is working. Saves ~200 tokens per research task.
- [ ] **Perplexity-style plan preview** — agent emits a numbered research plan before executing. Requires a planning step in the agent loop: Claude outputs a plan, we render it, then Claude executes. Consider whether this adds too much latency vs. the trust benefit.
- [ ] **Interleaved thinking blocks** — allow multiple ThinkingAccordions per message (one before each tool group), matching Claude.ai's interleaved thinking pattern. Requires the SSE thinking events from v1 step 5 to be in place first.
- [ ] **Citation hover snippets** — upgrade CitationBadge hover to show a snippet of the cited text (like Perplexity), not just the URL + title. Requires the agent to include `cited_text` in its citation format.

### References

- AG-UI Protocol: docs.ag-ui.com — standardized agent-to-UI event types
- Chainlit Steps: docs.chainlit.io/concepts/step — automatic parent/child step hierarchy
- PostHog blog: "8 learnings from 1 year of agents" — why they moved to graph workflows
- Vercel AI SDK: elements.ai-sdk.dev — `<Reasoning>` and `<ChainOfThought>` open-source components
