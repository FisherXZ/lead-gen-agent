# Tool Descriptions, Names & Schemas — Best Practices for LLM Tool Use

*Research date: 2026-05-17 · Audience: solar-gen agent on Claude, ~40 tools*

This note pulls together what Anthropic, OpenAI, the MCP working group, and the empirical-eval community currently say about the single most leveraged variable in agent quality: how each tool is *described* to the model. The goal is a checklist you can run any tool through before shipping it.

---

## 1. The headline claim everyone agrees on

> "Provide extremely detailed descriptions. This is by far the most important factor in tool performance." — Anthropic, *Define tools*

> "One of the most effective methods for improving tools is prompt-engineering your tool descriptions and specs." — Anthropic, *Writing effective tools for AI agents*

> "Write clear and detailed function names, parameter descriptions, and instructions." — OpenAI, *GPT-5 prompting guide*

ToolScan ([arXiv 2411.13547](https://arxiv.org/abs/2411.13547)) catalogs seven systematic failure modes; four — Incorrect Function Name, Incorrect Argument Name, Incorrect Argument Value, Incorrect Argument Type — are directly addressable by better names and descriptions. The Berkeley Function-Calling Leaderboard ([BFCL V4](https://gorilla.cs.berkeley.edu/leaderboard.html)) identifies "Relevance Detection" (knowing *not* to call a tool) as a major weakness, fixed by explicit "when NOT to use" language.

**Plain English:** The model picks a tool the way a junior engineer picks a function from autocomplete — by skimming the name and the first sentence of the doc. Get those two right and most other problems shrink.

---

## 2. Anthropic's official guidance (the canonical list)

From [platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools):

1. **Aim for at least 3–4 sentences per tool description, more if the tool is complex.** Explain: what it does, when to use it, when *not* to use it, what each parameter means, important caveats, what info the tool does *not* return.
2. **Consolidate related operations into fewer tools.** Prefer one `manage_pr(action=...)` over `create_pr` + `review_pr` + `merge_pr`. "Bloated tool sets that cover too much functionality or lead to ambiguous decision points about which tool to use" is identified as a top failure mode in [Writing tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents) — "if a human engineer can't definitively say which tool should be used in a given situation, an AI agent can't be expected to do better."
3. **Use meaningful namespacing in tool names** when tools span services: `github_list_prs`, `slack_send_message`. This is "especially important when using tool search."
4. **Use `input_examples` for complex tools**, not just descriptions. ~20–50 extra tokens for a simple example, ~100–200 for nested objects. Schema-validated; invalid examples return 400.
5. **Design responses to return only high-signal information.** Stable IDs (slugs, UUIDs), not opaque internal handles. "Bloated responses waste context and make it harder for Claude to extract what matters."
6. **The `description` field is plaintext.** It cannot contain XML tags (per the [Skills doc validation rules](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices), which apply analogously). Max 1024 chars for Skills; the tool-definition field is more generous but the spirit is the same: every token competes with conversation history once loaded.
7. **Write in third person, present tense.** "Processes Excel files and generates reports" — not "I can help with..." or "You can use this to..." (Skills best-practices doc; the warning applies to tool descriptions for the same reason — POV inconsistency causes discovery problems).
8. **Description should answer two questions:** *what* the tool does AND *when* to use it.

Anthropic's worked example (good vs bad) is short enough to quote verbatim:

> **Good:** "Retrieves the current stock price for a given ticker symbol. The ticker symbol must be a valid symbol for a publicly traded company on a major US stock exchange like NYSE or NASDAQ. The tool will return the latest trade price in USD. It should be used when the user asks about the current or most recent price of a specific stock. It will not provide any other information about the stock or company."
>
> **Bad:** "Gets the stock price for a ticker."

Notice what the good version does in 4 sentences: scope (US exchanges), unit (USD), trigger ("when the user asks about current/most recent price"), and *negative space* ("will not provide any other information").

---

## 3. OpenAI's guidance (function calling)

From the OpenAI Function Calling guide and the GPT-5 / GPT-4.1 prompting cookbooks:

- **"Make the functions obvious and intuitive."** Treat tool design as a software-engineering API design problem.
- **Aim for fewer than ~20 functions exposed at any one turn** — soft target. Beyond that, use a tool-search/retrieval layer to defer the long tail.
- **Combine functions always called in sequence.** If `mark_location()` always follows `query_location()`, fold the marking into the query.
- **Don't make the model fill arguments you already know.** If `order_id` is unambiguous from prior context, accept it as zero-arg `submit_refund()` and inject the `order_id` server-side.
- **Use enums and object structure to make invalid states unrepresentable.** Classic example: `toggle_light(on: bool, off: bool)` allows `{on:true, off:true}` — replace with `state: "on" | "off"`.
- **The "intern test":** "Can an intern/human correctly use the function given nothing but what you gave the model? If not, what questions do they ask you? Add the answers to the prompt."
- **Where guidance lives:** put per-tool semantics in the `description`; put cross-tool policy ("always confirm before deleting") in the system prompt.

OpenAI Agents SDK adds one more useful idiom — **start descriptions with "Use this when..."**: "Tool descriptions should be one or two sentences that start with 'Use this when…' so the model knows exactly when to pick the tool."

---

## 4. MCP spec — fields and annotations

[Model Context Protocol spec, 2025-11-25 server/tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools):

| Field | Purpose |
|---|---|
| `name` | Machine identifier. `^[a-zA-Z0-9_-]{1,64}$` |
| `title` | Optional human-readable display name (top-level as of 2025-11 spec; previously under `annotations.title`) |
| `description` | Plaintext, what + when + caveats |
| `inputSchema` | JSON Schema for arguments |
| `outputSchema` | (Optional) JSON Schema for structured output |
| `annotations.readOnlyHint` | True ⇒ tool does not modify environment |
| `annotations.destructiveHint` | True ⇒ may perform destructive (irreversible) updates. Default: true (worst-case) |
| `annotations.idempotentHint` | True ⇒ repeated calls with same args have no extra effect — enables safe retry |
| `annotations.openWorldHint` | True ⇒ interacts with external/untrusted entities (network, user-provided content) |

Critical caveat from the spec and the [MCP blog post on annotations](https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/): *annotations are hints, not guarantees.* "Clients should never make tool use decisions based on ToolAnnotations received from untrusted servers." Use them for UX (confirmation dialogs, auto-approve toggles, retry policy), not for security.

For solar-gen these map to concrete UX decisions:
- `readOnlyHint: true` ⇒ safe to auto-run with no permission prompt
- `destructiveHint: true` ⇒ require confirmation
- `idempotentHint: true` ⇒ retry on transient failure
- `openWorldHint: true` ⇒ treat output as untrusted (prompt-injection surface)

---

## 5. Empirical signal: what the benchmarks tell us

- **BFCL ([Patil et al., ICML 2025](https://proceedings.mlr.press/v267/patil25a.html)):** Seven categories — Simple, Multiple, Parallel, Nested, **Relevance Detection**, AST, Executable. Relevance Detection (knowing when *not* to call) is where frontier models still bleed accuracy. Implication: every tool needs an explicit "when not to use this" clause.
- **ToolScan ([arXiv 2411.13547](https://arxiv.org/abs/2411.13547)):** Seven empirically observed error patterns. Four are description-addressable: IFN (Incorrect Function Name — i.e., picked the wrong tool), IAN (Incorrect Argument Name), IAV (Incorrect Argument Value — includes missing required args), IAT (Incorrect Argument Type). The remaining three (IAC — too few calls; RAC — repeated identical calls; IFE — invalid format) are addressed by better system prompts and structured-output validation.
- **NexusRaven-V2 ([Nexusflow](https://github.com/nexusflowai/NexusRaven-V2)):** Standardizes tool docs as **Python docstrings**, often longer than OpenAI's 1024-char limit allows. The model "exhibits greater robustness than GPT-4 when handling variations in developers' descriptions" — i.e., richer descriptions improve generalization across phrasings.
- **When2Call ([NAACL 2025](https://aclanthology.org/2025.naacl-long.174.pdf)):** Documents the persistent problem of LLMs failing to *abstain* from tool calls when none are appropriate. Same lesson: surface the negative space.

**Plain English:** The benchmarks don't say "longer = better forever." They say models reliably break in four predictable ways, and three of those four are fixed by (a) better names and (b) explicit "when to use / when not to use" sections.

---

## 6. Concrete recommendations for solar-gen

### Length
- **Minimum:** 3 sentences (what / when / not when). Anything shorter routinely loses to a near-neighbor tool.
- **Sweet spot:** 4–8 sentences (≈80–200 tokens) for the majority of tools.
- **Long-form (300–600 tokens):** justified when the tool is complex, has many parameters, or sits next to a confusable neighbor (e.g., `web_search` vs `brave_search` vs `search_exa_people` — these *must* differentiate explicitly).
- **Parameter docs:** every parameter gets its own `description`, even if the name seems obvious. Examples inline (`"e.g. AAPL for Apple Inc."`) consistently outperform abstract descriptions.

### Naming
- `snake_case` (universally; LangChain, MCP, Anthropic examples).
- **Verb_object** when the tool is action-y: `send_message`, `create_pr`. **Noun-first** is acceptable for read-only retrievals: `permit_status`, `iso_queue_position`.
- **Namespace with a service prefix when overlap is possible:** `github_list_prs` not `list_prs`. Anthropic's blog explicitly calls this out for tool-search scenarios — which applies to solar-gen at ~40 tools.
- Avoid generic verbs that several tools could claim: `get`, `do`, `run`, `handle`. Prefer specific verbs that match the underlying domain action.
- Anthropic's Skills doc recommends gerund-form (`processing-pdfs`) for skills; for *tools* (callable functions) the convention is verb_object — gerunds read awkwardly when invoked.

### Where each piece of info lives
- **Tool `description`:** purpose, when to use, when not to use, what it returns, what it does *not* return, cost/latency hints, format conventions.
- **Parameter `description`:** what the value represents, format (`"ISO 8601 date"`), units (`"USD"`), examples (`"e.g. CAISO, ERCOT, MISO"`), defaults, enum semantics.
- **`input_examples`:** wire-format examples of how parameters compose. Use for nested/format-sensitive inputs.
- **System prompt:** cross-tool policy ("prefer `cached_search` over `web_search` when freshness is not critical"), retry policy, output style.

### Side effects
Use MCP annotations (or your equivalent metadata) for `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`. *Also* mention destructive behavior in the prose description — annotations are read by the harness, the description is read by the model.

### Error messages the LLM sees
This is under-appreciated in most guides. Bad tool errors send the model into retry loops. Good ones include:
- The error class (`PermissionDenied`, `NotFound`, `RateLimited`)
- A specific, actionable hint (`"Field 'signature_date' not found. Available fields: customer_name, order_total, signature_date_signed"` — from Anthropic's Skills examples)
- The recommended next action (`"Request access from owner or use different thread_id"`)
- If a different tool would work, *name it* (`"This file requires write access. Use create_or_update_file instead."`)

### Disambiguating similar tools (solar-gen-specific)
With overlapping search tools (`web_search`, `brave_search`, `search_exa_people`, `search_linkedin`), each description must answer one question crisply: **"What is true about my domain that is not true of the others?"** Examples:
- `web_search`: general-purpose web search via the Claude server-side tool. Returns titles + URLs. Use when freshness matters and the user hasn't specified a source. Mandatory `Sources:` section in the response.
- `brave_search`: privacy-respecting web search with independent index — use only when you need a non-Google viewpoint or web_search is rate-limited.
- `search_exa_people`: semantic search for individual people (name + role + employer). Returns LinkedIn-style profiles. Use when looking for *a specific person*; do NOT use for company-wide searches.
- `search_linkedin`: structured LinkedIn lookup by company or person URL. Use when you already have a LinkedIn handle/URL. NOT a substitute for `search_exa_people` (LinkedIn search has rate limits and weaker name resolution).

The pattern: each description includes an explicit *exclusion clause* naming the neighbor tool.

### Parameter design
- **Required vs optional:** mark only the truly load-bearing fields as required; everything else optional with sensible defaults documented inline.
- **Enums > free-form strings** wherever the value space is closed (countries, statuses, ISO regions). Models hallucinate fewer values when constrained.
- **Types that confuse models:** free-form date strings (always specify "ISO 8601 YYYY-MM-DD"), opaque IDs (prefer slugs), `Any`/untyped maps (split into structured object), booleans named with negatives (`disable_cache` — flip to `use_cache`).
- **Avoid mutually-exclusive booleans** (OpenAI's `toggle_light(on, off)` anti-pattern). Use a single enum.
- **Pagination:** if a tool could return >50 items, include `limit` (default 25), `cursor`, and document the default in the description — per Anthropic's [tool design ADR](https://github.com/vishnu2kmohan/mcp-server-langgraph/blob/main/adr/adr-0023-anthropic-tool-design-best-practices.md), restrict total response to ~25,000 tokens and truncate with a helpful message.

---

## 7. Annotated before/after examples

### Example 1 — Web search disambiguation

**Before**
```json
{
  "name": "brave_search",
  "description": "Search the web using Brave.",
  "input_schema": {
    "type": "object",
    "properties": {"q": {"type": "string"}},
    "required": ["q"]
  }
}
```
*Problems:* indistinguishable from any other `*_search`. No "when to use." Param named `q` not `query`. No "when NOT to use." Will lose every coin flip against `web_search`.

**After**
```json
{
  "name": "brave_search",
  "description": "Web search via the Brave independent index. Returns up to 20 results as {title, url, snippet, published_at}. Use this when (1) you need a non-Google viewpoint, (2) the primary `web_search` tool is rate-limited or returned no results, or (3) the user explicitly asks for Brave. Do NOT use for: searches that need very recent (<24h) news — `web_search` has fresher indexing; people-lookup — use `search_exa_people`; LinkedIn lookups — use `search_linkedin`. Costs ~1 API credit per call; latency ~800ms.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "Free-text search query. Quote phrases. Example: 'ERCOT interconnection queue 2026'."},
      "limit": {"type": "integer", "description": "Max results to return (1–20). Default 10.", "default": 10},
      "freshness": {"type": "string", "enum": ["day", "week", "month", "year", "all"], "description": "Time-bound filter on published_at. Default 'all'.", "default": "all"}
    },
    "required": ["query"]
  }
}
```

### Example 2 — A read-only lookup

**Before**
```json
{
  "name": "get_project",
  "description": "Get a project.",
  "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}
}
```

**After**
```json
{
  "name": "get_project",
  "description": "Retrieves a single solar-gen project record by ID, including site, status, ISO, capacity_mw, interconnection queue position, and the linked permit set. Use when you have a known project ID and need the canonical record. Returns null + 404 if the project does not exist. Does NOT return: per-permit comment threads (use `list_comments`), revenue forecasts (use `forecast_project_revenue`). Read-only; safe to call repeatedly.",
  "input_schema": {
    "type": "object",
    "properties": {
      "project_id": {"type": "string", "description": "Project slug (preferred) or UUID. Example slug: 'tx-permian-200mw-2026'."}
    },
    "required": ["project_id"]
  },
  "input_examples": [
    {"project_id": "tx-permian-200mw-2026"},
    {"project_id": "9e8c1a44-2c3b-4d59-9f7e-b0c9d8e7f6a5"}
  ]
}
```
Annotations: `readOnlyHint: true`, `idempotentHint: true`, `openWorldHint: false`.

### Example 3 — A destructive mutation

**Before**
```json
{
  "name": "delete_attachment",
  "description": "Deletes an attachment.",
  "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}
}
```

**After**
```json
{
  "name": "delete_attachment",
  "description": "Permanently deletes a project attachment. THIS OPERATION IS IRREVERSIBLE — there is no soft-delete or recycle bin. Use only when the user has explicitly confirmed deletion of a specific attachment by name or ID. Returns {deleted: true, id} on success. Returns 403 if the caller does not own the attachment — in that case, ask the owner instead of retrying. Do NOT use to 'clear' or 'reset' bulk attachments; there is no bulk delete by design. For replacing a file, use `update_attachment` instead.",
  "input_schema": {
    "type": "object",
    "properties": {
      "attachment_id": {"type": "string", "description": "UUID of the attachment to delete. Get this from `list_attachments` or `get_project`."}
    },
    "required": ["attachment_id"]
  }
}
```
Annotations: `readOnlyHint: false`, `destructiveHint: true`, `idempotentHint: true` (deleting an already-deleted attachment is a no-op 404), `openWorldHint: false`.

### Example 4 — Consolidating sibling tools

**Before** — three tools, all near-identical names, easy to confuse:
```
search_permits_by_state
search_permits_by_iso
search_permits_by_county
```

**After** — one tool with an explicit dispatch:
```json
{
  "name": "search_permits",
  "description": "Searches the permits database scoped to a US jurisdiction. Returns matching permits as {permit_id, project_name, status, filed_at, jurisdiction}. Exactly one of `state`, `iso`, or `county` must be set — the search is scoped to that level. Use `state` for state-level filings (PUC, DEP); `iso` for FERC/ISO interconnection queues (CAISO, ERCOT, MISO, PJM, SPP, NYISO, ISO-NE, MISO-S); `county` for local AHJ permits. Read-only. Results capped at 100; use `cursor` to paginate.",
  "input_schema": {
    "type": "object",
    "properties": {
      "state": {"type": "string", "description": "Two-letter US state code, e.g. 'TX', 'CA'."},
      "iso": {"type": "string", "enum": ["CAISO", "ERCOT", "MISO", "PJM", "SPP", "NYISO", "ISO-NE"], "description": "ISO/RTO code."},
      "county": {"type": "string", "description": "County name + state code, e.g. 'Permian, TX'."},
      "status": {"type": "string", "enum": ["filed", "in_review", "approved", "denied", "withdrawn"], "description": "Optional status filter."},
      "cursor": {"type": "string", "description": "Pagination cursor from previous response."}
    },
    "required": []
  }
}
```
This collapses three tools into one, removes ambiguity ("which `search_permits_*` do I call?"), and uses enums where the value space is closed. Matches Anthropic's "consolidate related operations" guidance directly.

### Example 5 — A real Claude Code description (good)

The Claude Code `Read` tool description, paraphrased from the system prompt visible in this session:

> Reads a file from the local filesystem. You can access any file directly. Assume this tool can read all files on the machine. If the User provides a path, assume that path is valid. It is okay to read a file that does not exist; an error will be returned.
>
> Usage notes:
> - `file_path` must be an absolute path, not relative.
> - Reads up to 2000 lines starting from the beginning by default.
> - Use `offset`/`limit` for targeted reads of large files.
> - Returns content in `cat -n` format with line numbers starting at 1.
> - For images (PNG, JPG): contents are presented visually since Claude is multimodal.
> - For PDFs: large PDFs (>10 pages) require a `pages` parameter. Max 20 pages per request.
> - For Jupyter notebooks: returns all cells with outputs.
> - This tool can only read files, not directories.

What it does well: (1) starts with the action verb, (2) sets expectations about path resolution, (3) tells the model it's OK to attempt to read a missing file (preventing pre-flight overthinking), (4) enumerates every special content type and how it behaves, (5) ends with a sharp boundary ("only files, not directories") which prevents the most common confusion with `Glob`/`ls`.

---

## 8. Checklist — run every tool description through this

**Naming**
- [ ] `snake_case`, ≤64 chars, matches `^[a-zA-Z0-9_-]{1,64}$`
- [ ] Verb_object (action tools) or noun-first (read-only retrievals)
- [ ] Namespaced with service prefix when overlap with sibling tools is possible
- [ ] No generic verbs (`get`, `do`, `run`) without a specific object
- [ ] Pronounceable; a teammate could guess what it does from the name alone

**Description (prose)**
- [ ] At least 3 sentences (what / when to use / when NOT to use); 4–8 for typical tools
- [ ] Third person, present tense ("Retrieves...", not "I will retrieve...")
- [ ] States what the tool returns AND what it does NOT return
- [ ] Names confusable sibling tools explicitly ("Do NOT use for X — use `other_tool` instead")
- [ ] Mentions cost/latency if non-trivial
- [ ] Mentions destructive behavior in prose even if also marked in annotations
- [ ] No XML tags inside the description string (Anthropic constraint)
- [ ] Plaintext; no markdown headers that might confuse rendering

**Parameters**
- [ ] Every param has a `description` — even obvious ones
- [ ] Format/units/examples inline ("e.g. AAPL", "ISO 8601 date", "USD")
- [ ] Enums where value space is closed
- [ ] Only truly required fields marked `required`
- [ ] Defaults documented in the param description
- [ ] No mutually-exclusive booleans (use an enum)
- [ ] No untyped `Any` maps (split into structured object)
- [ ] Booleans named positively (`use_cache`, not `disable_cache`)
- [ ] Param names are specific (`project_id`, `thread_id`) not generic (`id`)

**Examples**
- [ ] `input_examples` provided for any tool with nested objects or format-sensitive params
- [ ] Examples cover: minimum-required case, full case, common edge case
- [ ] All examples validate against `input_schema`

**Side-effect metadata**
- [ ] `readOnlyHint` set
- [ ] `destructiveHint` set (default to `true` unless explicitly safe)
- [ ] `idempotentHint` set (informs the harness's retry policy)
- [ ] `openWorldHint` set (informs prompt-injection treatment of output)

**Errors the model will see**
- [ ] Errors include a class name and a specific actionable hint
- [ ] If a different tool would succeed, the error names it
- [ ] No bare HTTP status codes — always include semantic text

**Final sanity checks**
- [ ] **Intern test:** could a new hire use this tool from the description alone?
- [ ] **Disambiguation test:** if you removed the tool name and showed just the description, could a teammate pick this tool from the lineup?
- [ ] **Confusable-pair test:** for every near-neighbor tool, the description explicitly says when to prefer this one
- [ ] **Token budget:** description + schema fits in ≤500 tokens (most tools); ≤1500 for complex ones
- [ ] **Negative-space test:** at least one "do NOT use for…" clause exists

---

## Plain English

We have 40 tools and a model that picks one per turn. The model picks well or badly almost entirely based on what we wrote in each tool's `name` and `description`. Every authoritative source says the same three things: write detailed descriptions (3+ sentences minimum), always say when *not* to use a tool (especially when there's a near-twin that does something similar), and design parameters so the wrong thing can't be expressed (enums, required-vs-optional, no booleans that contradict each other). The empirical benchmarks (BFCL, ToolScan) confirm that "picked the wrong tool" and "made up an argument name" are by far the most common failures — both fixable by better text. The MCP annotations (`readOnlyHint` etc.) are for the *harness* — they tell solar-gen whether to ask the user for permission or auto-retry — and don't substitute for clear prose telling the *model* what's safe.

---

## Sources

- [Anthropic — Define tools (best practices)](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools)
- [Anthropic — Tool use overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
- [Anthropic Engineering — Writing effective tools for AI agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Anthropic Engineering — Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Anthropic — Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- [Anthropic — Prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)
- [OpenAI — Function calling guide](https://platform.openai.com/docs/guides/function-calling)
- [OpenAI Cookbook — GPT-5 prompting guide](https://cookbook.openai.com/examples/gpt-5/gpt-5_prompting_guide)
- [OpenAI Cookbook — GPT-4.1 prompting guide](https://cookbook.openai.com/examples/gpt4-1_prompting_guide)
- [OpenAI Agents SDK — Handoffs](https://openai.github.io/openai-agents-python/handoffs/)
- [MCP — Server tools spec (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- [MCP blog — Tool annotations as risk vocabulary](https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/)
- [BFCL V4 — Berkeley Function-Calling Leaderboard](https://gorilla.cs.berkeley.edu/leaderboard.html)
- [BFCL paper — From tool use to agentic evaluation (ICML 2025)](https://proceedings.mlr.press/v267/patil25a.html)
- [ToolScan — A benchmark for characterizing errors in tool-use LLMs (arXiv 2411.13547)](https://arxiv.org/abs/2411.13547)
- [When2Call — When (not) to call tools (NAACL 2025)](https://aclanthology.org/2025.naacl-long.174.pdf)
- [NexusRaven-V2 — Open-source function-calling LLM](https://github.com/nexusflowai/NexusRaven-V2)
- [LangChain — Tools documentation](https://docs.langchain.com/oss/python/langchain/tools)
- [Anthropic tool design best-practices ADR (third-party)](https://github.com/vishnu2kmohan/mcp-server-langgraph/blob/main/adr/adr-0023-anthropic-tool-design-best-practices.md)
- [Piebald-AI — Claude Code system prompts (WebSearch)](https://github.com/Piebald-AI/claude-code-system-prompts/blob/main/system-prompts/tool-description-websearch.md)
