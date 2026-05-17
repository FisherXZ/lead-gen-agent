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

## 2. Anthropic's official guidance

From [platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools):

1. **≥3–4 sentences per description, more if complex.** Explain what it does, when to use it, when NOT to use it, parameter semantics, caveats, what it does *not* return.
2. **Consolidate related operations.** Prefer `manage_pr(action=...)` over `create_pr` + `review_pr` + `merge_pr`. From [Writing tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents): "if a human engineer can't definitively say which tool should be used in a given situation, an AI agent can't be expected to do better."
3. **Namespace when tools span services:** `github_list_prs`, `slack_send_message`. Especially important with tool search.
4. **`input_examples` for complex/nested/format-sensitive inputs.** ~20–50 tokens simple, ~100–200 nested. Schema-validated.
5. **Return only high-signal data.** Stable IDs (slugs, UUIDs), not opaque handles. "Bloated responses waste context and make it harder for Claude to extract what matters."
6. **`description` is plaintext, no XML tags.** Skills limit is 1024 chars; tool-definition field is more generous but every token competes with conversation history once loaded.
7. **Third person, present tense.** "Retrieves..." not "I can help you..." or "You can use this to..." — inconsistent POV causes discovery problems.
8. **Always answer two questions:** *what* the tool does AND *when* to use it.

Anthropic's worked example:

> **Good:** "Retrieves the current stock price for a given ticker symbol. The ticker symbol must be a valid symbol for a publicly traded company on a major US stock exchange like NYSE or NASDAQ. The tool will return the latest trade price in USD. It should be used when the user asks about the current or most recent price of a specific stock. It will not provide any other information about the stock or company."
>
> **Bad:** "Gets the stock price for a ticker."

Four sentences, four jobs: scope (US exchanges), unit (USD), trigger, and negative space ("will not provide any other information").

---

## 3. OpenAI's guidance

From the [OpenAI Function Calling guide](https://platform.openai.com/docs/guides/function-calling) and the [GPT-5 prompting cookbook](https://cookbook.openai.com/examples/gpt-5/gpt-5_prompting_guide):

- **"Make the functions obvious and intuitive."** Treat tool design as API design.
- **Aim for fewer than ~20 functions per turn** (soft target). Above that, use tool search to defer the long tail.
- **Combine functions always called in sequence.** If `mark_location()` always follows `query_location()`, fold them.
- **Don't make the model fill arguments you already know.** If `order_id` is unambiguous from context, accept a zero-arg `submit_refund()` and inject the ID server-side.
- **Enums and structure make invalid states unrepresentable.** Replace `toggle_light(on: bool, off: bool)` with `state: "on" | "off"`.
- **The "intern test":** "Can an intern/human correctly use the function given nothing but what you gave the model?"
- **Per-tool semantics → `description`; cross-tool policy → system prompt.**

[OpenAI Agents SDK](https://openai.github.io/openai-agents-python/handoffs/) adds: **start descriptions with "Use this when..."** so the model can pattern-match selection cues.

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

Critical caveat ([MCP blog on annotations](https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/)): *annotations are hints, not guarantees.* "Clients should never make tool use decisions based on ToolAnnotations received from untrusted servers." Use them for UX (confirmation dialogs, auto-approve, retry policy), not for security. For solar-gen: `readOnlyHint` ⇒ auto-run; `destructiveHint` ⇒ require confirmation; `idempotentHint` ⇒ retry on transient failure; `openWorldHint` ⇒ treat output as untrusted (prompt-injection surface).

---

## 5. Empirical signal

- **[BFCL](https://gorilla.cs.berkeley.edu/leaderboard.html)** (Patil et al., ICML 2025): Seven evaluation categories. Relevance Detection — knowing when *not* to call — is where frontier models still lose accuracy. Every tool needs an explicit "when NOT to use" clause.
- **[ToolScan](https://arxiv.org/abs/2411.13547)**: Seven empirical error patterns. Four are description-addressable: IFN (wrong tool picked), IAN (hallucinated argument name), IAV (wrong / missing required value), IAT (wrong type). The other three (too few calls, repeated calls, invalid format) are system-prompt and schema-validation territory.
- **[NexusRaven-V2](https://github.com/nexusflowai/NexusRaven-V2)**: Standardizes docs as Python docstrings (often >1024 chars). The model "exhibits greater robustness than GPT-4 when handling variations in developers' descriptions" — richer descriptions generalize across phrasings.
- **[When2Call](https://aclanthology.org/2025.naacl-long.174.pdf)** (NAACL 2025): LLMs persistently fail to *abstain* when no tool fits. Surface the negative space.

**Plain English:** Models break in predictable ways — three of the top four failure modes are fixed by better names and explicit "when to use / when not to use" sections.

---

## 6. Concrete recommendations for solar-gen

### Length
- **Minimum 3 sentences** (what / when / not when). Anything shorter loses to confusable neighbors.
- **Sweet spot: 4–8 sentences (~80–200 tokens)** for typical tools.
- **Long-form (300–600 tokens)** when the tool has many params, complex semantics, or a near-twin (e.g., `web_search` vs `brave_search` vs `search_exa_people` — these *must* differentiate explicitly).
- **Every parameter gets a `description`**, even obvious ones. Inline examples (`"e.g. AAPL for Apple Inc."`) consistently outperform abstract phrasing.

### Naming
- `snake_case`, ≤64 chars, matches `^[a-zA-Z0-9_-]{1,64}$`.
- **Verb_object** for actions (`send_message`, `create_pr`); **noun-first** acceptable for read-only retrievals (`permit_status`).
- **Service prefix when overlap is possible:** `github_list_prs` not `list_prs`. Critical at solar-gen's ~40-tool scale.
- Avoid generic verbs (`get`, `do`, `run`, `handle`) — they invite collisions.
- Skills use gerund form (`processing-pdfs`); *tools* use verb_object — gerunds read awkwardly when called.

### Where each piece of info lives
- **Tool `description`:** purpose, when, when-not, what's returned, what's NOT returned, cost/latency, format conventions.
- **Parameter `description`:** semantics, format (`"ISO 8601 date"`), units (`"USD"`), examples, defaults, enum meanings.
- **`input_examples`:** wire-format examples for nested/format-sensitive inputs.
- **System prompt:** cross-tool policy ("prefer `cached_search` when freshness is not critical"), retry policy, output style.

### Side effects
Set MCP annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`). *Also* mention destructive behavior in prose — annotations are read by the harness, descriptions by the model.

### Error messages the LLM sees
Under-appreciated; bad errors send the model into retry loops. Good errors include:
- Error class (`PermissionDenied`, `NotFound`, `RateLimited`)
- A specific actionable hint — Anthropic's example: `"Field 'signature_date' not found. Available fields: customer_name, order_total, signature_date_signed"`
- Recommended next action (`"Request access from owner or use different thread_id"`)
- If a different tool would succeed, *name it* (`"This file requires write access. Use create_or_update_file instead."`)

### Disambiguating similar tools
With overlapping search tools (`web_search`, `brave_search`, `search_exa_people`, `search_linkedin`), each description must answer: **"What is true of my domain that is not true of the others?"** Every description includes an explicit *exclusion clause* naming the neighbor tool ("Do NOT use for people-lookup — use `search_exa_people`"). See Example 1 below for the pattern.

### Parameter design
- Mark only truly load-bearing fields as `required`; everything else optional with documented defaults.
- **Enums beat free-form strings** wherever the value space is closed (statuses, ISO codes, regions). Reduces hallucinated values.
- Confusing types to avoid: free-form dates (specify "ISO 8601 YYYY-MM-DD"), opaque IDs (prefer slugs), `Any`/untyped maps, negatively-named booleans (`disable_cache` → flip to `use_cache`).
- Avoid mutually-exclusive booleans (`toggle_light(on, off)`); use a single enum.
- For lists >50 items: include `limit` (default 25) and `cursor`; cap responses around 25k tokens with a helpful truncation message (per the [Anthropic tool-design ADR](https://github.com/vishnu2kmohan/mcp-server-langgraph/blob/main/adr/adr-0023-anthropic-tool-design-best-practices.md)).

---

## 7. Annotated before/after examples

### Example 1 — Web search disambiguation

**Before:** `description: "Search the web using Brave."`, param `q: string`. Indistinguishable from any other `*_search`. No "when to use", no "when NOT to use", terse param. Loses every coin flip against `web_search`.

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

**Before:** `description: "Get a project."`, parameter `id: string` (no description).

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
  "input_examples": [{"project_id": "tx-permian-200mw-2026"}]
}
```
Annotations: `readOnlyHint: true`, `idempotentHint: true`, `openWorldHint: false`. Before-version errors are 50/50: model would call `list_projects` instead, or hallucinate UUIDs.

### Example 3 — A destructive mutation

**Before:** `description: "Deletes an attachment."`, parameter `id: string`.

**After**
```json
{
  "name": "delete_attachment",
  "description": "Permanently deletes a project attachment. THIS OPERATION IS IRREVERSIBLE — there is no soft-delete or recycle bin. Use only when the user has explicitly confirmed deletion of a specific attachment by name or ID. Returns {deleted: true, id} on success. Returns 403 if the caller does not own the attachment — in that case, ask the owner instead of retrying. Do NOT use to 'clear' or 'reset' bulk attachments; there is no bulk delete by design. To replace a file, use `update_attachment` instead.",
  "input_schema": {
    "type": "object",
    "properties": {
      "attachment_id": {"type": "string", "description": "UUID of the attachment to delete. Get this from `list_attachments` or `get_project`."}
    },
    "required": ["attachment_id"]
  }
}
```
Annotations: `destructiveHint: true`, `idempotentHint: true` (deleting an already-deleted attachment is a no-op 404), `openWorldHint: false`. The shouting capitals on "IRREVERSIBLE" are intentional — models attend more reliably to emphasized text in tool descriptions.

### Example 4 — Consolidating sibling tools

**Before** — three tools, easy to confuse: `search_permits_by_state`, `search_permits_by_iso`, `search_permits_by_county`.

**After** — one tool with explicit dispatch:
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

### Example 5 — A real Claude Code description (annotated)

Claude Code's `Read` tool description, paraphrased from this session's system prompt:

> Reads a file from the local filesystem. Assume this tool can read all files on the machine. If the User provides a path, assume that path is valid. It is okay to read a file that does not exist; an error will be returned.
>
> Usage: `file_path` must be absolute; reads up to 2000 lines by default; use `offset`/`limit` for large files; returns `cat -n` format with line numbers; images presented visually (multimodal); PDFs >10 pages require `pages` (max 20/request); Jupyter notebooks return all cells with outputs; **this tool can only read files, not directories**.

What it does well: (1) starts with action verb; (2) sets path-resolution expectations; (3) tells the model it's safe to attempt a missing file (prevents pre-flight overthinking); (4) enumerates every special content type; (5) ends with a sharp negative-space boundary ("only files, not directories") that prevents confusion with `Glob`/`ls`.

---

## 8. Checklist — run every tool description through this

**Naming**
- [ ] `snake_case`, ≤64 chars, matches `^[a-zA-Z0-9_-]{1,64}$`
- [ ] Verb_object (action) or noun-first (read-only retrieval)
- [ ] Service prefix when overlap is possible
- [ ] No generic verbs (`get`, `do`, `run`, `handle`) standing alone

**Description**
- [ ] ≥3 sentences (what / when / when-not); 4–8 for typical tools
- [ ] Third person, present tense; no "I" or "you"
- [ ] States what it returns AND what it does NOT return
- [ ] Names confusable sibling tools explicitly ("Do NOT use for X — use `other_tool`")
- [ ] Mentions cost/latency if non-trivial
- [ ] Mentions destructive behavior in prose, not just annotations
- [ ] Plaintext only; no XML tags inside the string

**Parameters**
- [ ] Every param has a `description`
- [ ] Format/units/examples inline ("e.g. AAPL", "ISO 8601 date", "USD")
- [ ] Enums wherever value space is closed
- [ ] Only truly load-bearing fields are `required`
- [ ] Defaults documented in the param description
- [ ] No mutually-exclusive booleans
- [ ] No untyped `Any` maps
- [ ] Booleans named positively (`use_cache`, not `disable_cache`)
- [ ] Specific param names (`project_id`, not `id`)

**Examples**
- [ ] `input_examples` for any tool with nested or format-sensitive params
- [ ] Cover minimum-required, full, and common-edge cases
- [ ] All examples validate against `input_schema`

**Side-effect metadata** (MCP annotations or equivalent)
- [ ] `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` all set

**Errors the model will see**
- [ ] Error class + specific actionable hint
- [ ] If a different tool would succeed, name it
- [ ] No bare HTTP codes — always include semantic text

**Final sanity checks**
- [ ] **Intern test:** a new hire could use this tool from the description alone
- [ ] **Disambiguation test:** with the name hidden, a teammate could still pick this tool from the lineup
- [ ] **Confusable-pair test:** every near-neighbor is named in an exclusion clause
- [ ] **Token budget:** description + schema ≤500 tokens (most); ≤1500 (complex)
- [ ] **Negative-space test:** at least one "do NOT use for…" clause

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
