# Tool Directory Refactor — Unified Agent Architecture

**Date:** 2026-03-08
**Status:** In Progress
**Depends on:** Informs `2026-03-08-agent-v2-improvements.md`

---

## Goal

Replace the current two-agent architecture (chat agent delegates to research agent) with a **single unified agent** that has direct access to all tools. Establish a `tools/` directory structure that makes adding new tools trivial.

---

## Current Architecture (Problems)

```
chat_agent.py          agent.py
├── search_projects    ├── web_search (Tavily)
├── research_epc ──────┤── report_findings
├── batch_research_epc─┘
├── get_discoveries
├── query_knowledge_base
```

- **Double LLM cost**: Chat agent reasons about what to research, then research agent re-reads project info and reasons about how to research. Context loaded twice.
- **No context sharing**: User hints in chat ("I think it's McCarthy") can't flow into the research agent — `research_epc` takes a bare `project_id`.
- **Tool definitions scattered**: Defined inline in two files (`agent.py:18-99`, `chat_agent.py:56-196`), mixed with execution logic.
- **Adding a tool requires editing multiple files**: Definition, handler, imports, wiring — all interleaved with unrelated code.

---

## New Architecture

```
agent/src/
├── tools/                    # Tool directory
│   ├── __init__.py           # Registry: get_all_tools(), get_tool_handler()
│   ├── _base.py              # ToolDef type, shared helpers
│   ├── web_search.py         # Tavily search
│   ├── fetch_page.py         # Full page scraping (Change 4 from v2 plan)
│   ├── search_projects.py    # DB project search
│   ├── get_discoveries.py    # Lookup past research
│   ├── query_kb.py           # Knowledge base queries
│   ├── report_findings.py    # Structured EPC result output
│   └── request_guidance.py   # Human-in-the-loop (Change 7, future)
│
├── chat_agent.py             # Unified streaming agent (all tools)
├── research.py               # Lightweight research runner (for batch + button)
├── batch.py                  # Concurrent batch runner (calls research.py)
├── prompts.py                # System prompts (chat + research)
├── models.py                 # Pydantic schemas
├── db.py                     # Supabase client
├── knowledge_base.py         # KB read/write
├── sse.py                    # SSE protocol
└── main.py                   # FastAPI routes
```

### Key Design Decisions

**1. Each tool = one file with a standard structure**

Every tool file exports two things:
- `DEFINITION`: The Claude tool schema (name, description, input_schema)
- `execute(input: dict) -> dict`: The async handler

```python
# tools/web_search.py

DEFINITION = {
    "name": "web_search",
    "description": "...",
    "input_schema": { ... }
}

async def execute(tool_input: dict) -> dict:
    """Run a Tavily web search."""
    ...
```

This convention means adding a new tool is: create one file, drop it in `tools/`. The registry auto-discovers it.

**2. Registry handles discovery and dispatch**

```python
# tools/__init__.py

def get_all_tools() -> list[dict]:
    """Return all tool definitions for Claude API calls."""

def get_tools(names: list[str]) -> list[dict]:
    """Return specific tool definitions by name."""

async def execute_tool(name: str, tool_input: dict) -> dict:
    """Dispatch to the right handler."""
```

The chat agent calls `get_all_tools()` to get every tool. The research runner calls `get_tools(["web_search", "fetch_page", "report_findings"])` to get only research tools. No hardcoded lists — the registry is the source of truth.

**3. Chat agent gets all tools directly**

The merged chat agent has direct access to `web_search`, `fetch_page`, `report_findings`, etc. When a user says "research this project," the chat agent searches the web *itself* — no delegation to a sub-agent. User context (hints, corrections, conversation history) flows naturally into the research.

**4. Research runner stays for batch + button**

`research.py` replaces `agent.py` as a thin wrapper:

```python
async def run_research(project: dict, knowledge_context: str | None = None) -> tuple[AgentResult, list[dict], int]:
    """Run EPC research as a standalone (non-chat) operation.

    Used by: batch runs, ResearchButton API endpoint.
    Uses the same tools as the chat agent but with a focused
    research-only system prompt and no conversation context.
    """
```

This is NOT a second agent — it's the same Claude call with the same shared tools, just a different system prompt (research-focused, no chat fluff) and no SSE streaming.

**5. Tool subsets per context**

Not every tool makes sense everywhere:

| Tool | Chat Agent | Research Runner | Batch |
|------|-----------|-----------------|-------|
| web_search | Yes | Yes | Yes |
| fetch_page | Yes | Yes | Yes |
| report_findings | Yes | Yes | Yes |
| search_projects | Yes | No | No |
| get_discoveries | Yes | No | No |
| query_kb | Yes | No | No |
| request_guidance | Yes | No | No |

The registry supports this via `get_tools(names)` for selective loading.

---

## Tool Definitions — Comprehensive Descriptions

Each tool description needs to tell Claude **when** to use it, **what** it returns, and **what NOT** to use it for. Current descriptions are too terse. Here's the standard:

```python
DEFINITION = {
    "name": "tool_name",
    "description": (
        # Line 1: What it does (one sentence)
        "Search the web for information using Tavily search engine. "
        # Line 2: When to use it
        "Use this for initial discovery searches — finding press releases, "
        "trade articles, and news about solar projects and EPC contractors. "
        # Line 3: What it returns
        "Returns up to 10 results with title, URL, and content snippet (~200 chars). "
        # Line 4: Limitations or when NOT to use it
        "Snippets are short — if a result looks promising, use fetch_page to read the full article."
    ),
    "input_schema": { ... }
}
```

---

## Detailed File Specifications

### `tools/_base.py`

```python
"""Shared types and helpers for tool modules."""

from typing import TypedDict

class ToolDef(TypedDict):
    name: str
    description: str
    input_schema: dict

def validate_uuid(value: str) -> bool:
    """Check if a string is a valid UUID."""
    ...
```

### `tools/__init__.py`

```python
"""Tool registry — auto-discovers and dispatches tools."""

from . import (
    web_search,
    fetch_page,
    search_projects,
    get_discoveries,
    query_kb,
    report_findings,
)

# Module-level registry: name -> module
_TOOLS = {
    mod.DEFINITION["name"]: mod
    for mod in [
        web_search,
        fetch_page,
        search_projects,
        get_discoveries,
        query_kb,
        report_findings,
    ]
}

def get_all_tools() -> list[dict]:
    """All tool definitions."""
    return [mod.DEFINITION for mod in _TOOLS.values()]

def get_tools(names: list[str]) -> list[dict]:
    """Specific tool definitions by name."""
    return [_TOOLS[n].DEFINITION for n in names if n in _TOOLS]

async def execute_tool(name: str, tool_input: dict) -> dict:
    """Dispatch to handler. Raises KeyError for unknown tools."""
    return await _TOOLS[name].execute(tool_input)
```

### `tools/web_search.py`

Migrates from `tavily_search.py`. Same Tavily client + cache, but now as a tool module.

### `tools/fetch_page.py`

New tool (Change 4 from v2 plan). `httpx` + `trafilatura` page scraping.

### `tools/search_projects.py`

Migrates the `search_projects` tool definition + handler from `chat_agent.py:56-117` and `chat_agent.py:214-229`.

### `tools/get_discoveries.py`

Migrates from `chat_agent.py:156-173` and `chat_agent.py:282-288`.

### `tools/query_kb.py`

Migrates from `chat_agent.py:174-196` and `chat_agent.py:290-296`.

### `tools/report_findings.py`

Migrates from `agent.py:43-98`. The handler parses input into `AgentResult` and returns it. In the chat agent context, this signals "research complete" — the agent will summarize findings in its next text response.

---

## Migration Plan

### Step 1: Create `tools/` directory with all tool modules
- Create `_base.py`, `__init__.py`
- Move `web_search` from `tavily_search.py` → `tools/web_search.py`
- Move `search_projects` handler from `chat_agent.py` → `tools/search_projects.py`
- Move `get_discoveries` handler from `chat_agent.py` → `tools/get_discoveries.py`
- Move `query_kb` handler from `chat_agent.py` → `tools/query_kb.py`
- Move `report_findings` from `agent.py` → `tools/report_findings.py`
- Create `tools/fetch_page.py` (new)

### Step 2: Create `research.py`
- Lightweight replacement for `agent.py`
- Uses `tools.get_tools(["web_search", "fetch_page", "report_findings"])`
- Uses `tools.execute_tool()` for dispatch
- Keeps the same `run_research()` → `(AgentResult, log, tokens)` interface

### Step 3: Refactor `chat_agent.py`
- Remove inline tool definitions — use `tools.get_all_tools()`
- Remove `_execute_tool()` — use `tools.execute_tool()`
- Remove `research_epc` and `batch_research_epc` delegation tools
- Agent now has `web_search`, `fetch_page`, `report_findings` directly
- Update system prompt to reflect direct research capability

### Step 4: Update `batch.py`
- Import from `research.py` instead of `agent.py`
- No other changes needed

### Step 5: Update `main.py`
- `/api/discover` endpoint uses `research.run_research()` instead of `agent.run_agent()`
- Everything else stays the same

### Step 6: Clean up
- Delete `agent.py` (replaced by `research.py`)
- Delete `tavily_search.py` (moved to `tools/web_search.py`)
- Update imports across the codebase

---

## Chat Agent System Prompt (Updated)

The merged agent needs a system prompt that covers both conversational and research capabilities:

```
You are an AI assistant for Civ Robotics that helps explore solar energy projects
and discover EPC contractors.

## Your Capabilities
- Search the project database by state, region, capacity, developer, etc.
- Search the web for EPC contractor information (press releases, trade articles, portfolios)
- Read full web pages when search snippets aren't enough
- Report structured EPC findings with confidence levels and sources
- Query the knowledge base for developer/EPC profiles and relationships
- Look up existing EPC discovery results

## When Researching EPCs
[... research-specific instructions from prompts.py SYSTEM_PROMPT ...]
[... verification mindset, confidence levels, source rankings ...]

## General Conversation
- Be concise. Summarize search results briefly.
- Use state abbreviations (TX, CA, IL).
- Default COD filter: 2025–2028.
```

The research instructions are included in the main prompt but scoped under a "When Researching EPCs" section so they don't interfere with casual project searches.

---

## Adding a New Tool (Future Developer Guide)

To add a new tool:

1. Create `tools/my_tool.py`:
```python
DEFINITION = {
    "name": "my_tool",
    "description": "...",
    "input_schema": { ... }
}

async def execute(tool_input: dict) -> dict:
    ...
```

2. Register in `tools/__init__.py`:
```python
from . import my_tool
# Add to _TOOLS dict
```

3. If the tool should only be available in certain contexts, update the `get_tools()` calls in `research.py` or `chat_agent.py`.

That's it. No other files need to change.
