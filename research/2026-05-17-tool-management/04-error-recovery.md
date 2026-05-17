# Tool Failure Handling, Error Recovery, and Self-Correction in LLM Agents

**Date:** 2026-05-17
**Scope:** Production patterns for tool-call failures in Claude-based agents, with concrete recommendations for solar-gen's `runtime/escalation.py` and tool base class.

---

## Plain English

When a tool inside the agent breaks — the network blips, HubSpot rate-limits us, a scraper finds nothing, the model passes the wrong arguments — somebody has to decide: do we silently retry, do we tell the model what went wrong and let it try again, or do we stop and ask the human? The boring middle answer is the right one most of the time: catch the error in the runtime, turn it into a *useful sentence the model can act on*, and only stop after several attempts or when the action is irreversible (e.g. writing to HubSpot). The single highest-leverage lever isn't retry math — it's the wording of the error string returned to the model. Good error strings tell the model the *cause* and a *concrete next action*; bad ones dump a stack trace and the model loops. This document collects what production agent frameworks do and turns it into a short list of changes for solar-gen.

---

## 1. Error Taxonomy

Across production frameworks, tool errors split along three roughly orthogonal axes:

| Axis | Categories | Who handles it |
|------|-----------|----------------|
| **Origin** | Infrastructure (network, 5xx, timeout) / API contract (4xx, auth, quota) / Tool semantics ("no results", "not found") / Model fault (bad args, hallucinated tool) | Mixed |
| **Retriability** | Transient (retry with backoff) / Permanent (don't retry) / Idempotent-only retriable | Runtime |
| **Recoverability** | Runtime-fixable (retry, fall back) / Model-fixable (re-call with corrected args) / Human-fixable (escalate) | Differs |

**LangChain** centralizes this around `ToolException`. By raising `ToolException`, a tool signals "this is a known failure, don't crash the agent." The executor then consults `handle_tool_error`, which can be `True` (stringify the exception), a string (return that string), or a callable that takes the exception and returns a string fed back to the model as the tool's observation ([LangChain — How to handle tool errors](https://python.langchain.com/docs/how_to/tools_error/), [`ToolException` API ref](https://python.langchain.com/api_reference/core/tools/langchain_core.tools.base.ToolException.html)). Unhandled exceptions still crash the agent — explicit opt-in is required.

**OpenAI Agents SDK** has the same shape but a different name: `failure_error_function`. The string it returns is fed back to the model as the tool's output, "allowing the LLM to 'see' the error and attempt a fix or move on." If explicitly set to `None`, tool errors propagate and stop the run; if unset, the SDK's `default_tool_error_function` is used ([Error Recovery Patterns — DeepWiki](https://deepwiki.com/openai/openai-agents-python/14.2-multi-agent-orchestration-examples)). Model-API failures (not tool failures) are handled by a separate `ModelSettings(retry=...)` policy that receives a `RetryPolicyContext` and returns a decision.

**MCP** distinguishes *protocol-level* errors (JSON-RPC errors, client-side, surfaced as a UI notification and not shown to the LLM) from *tool-call* errors. Tool errors are returned as a normal `CallToolResult` with `isError: true` and a `content` array — they go *into the LLM context*. The MCP spec explicitly notes the content "should not be a raw stack trace … it should be a descriptive message helping the model understand what went wrong" ([MCP — Tools concepts](https://modelcontextprotocol.info/docs/concepts/tools/), [Alpic — better MCP error responses](https://alpic.ai/blog/better-mcp-tool-call-error-responses-ai-recover-gracefully)).

**Letta** does not classify errors per se — it constrains *which tools can run next* via `InitToolRule`, `ToolRule(children=...)`, and `TerminalToolRule`. This sidesteps a class of "error" (model picks a tool that doesn't make sense in the current state) by making the choice unrepresentable ([Letta — Creating Tool Rules](https://docs.letta.com/guides/agents/tool-rules)).

**smolagents** runs the agent's *code* (not just JSON tool calls) and surfaces tool failures as `AgentError` subclasses with the full Python traceback appended to memory: `"Error in tool call execution: {tool_name}() got an unexpected keyword argument..."` ([smolagents source](https://github.com/huggingface/smolagents/blob/main/src/smolagents/agents.py)). The model sees the traceback and is expected to "reverse-engineer the tool to fix the errors" — a Voyager-style approach.

**Solar-gen today** has a flat taxonomy in `tools/__init__.py::execute_tool`: `validation_error`, `api_key_missing`, `search_tool_error`, `tool_error`. This is a reasonable starting point but conflates retriability with origin (e.g., `search_tool_error` covers both 5xx and 408 timeouts, which retry, and 401, which does not).

---

## 2. Retry Strategy

**Where retries live.** Three layers, choose deliberately:

1. **Inside the tool** (SDK retries, e.g., `tenacity.retry` around a Tavily call). Hidden from the model. Best for transient infrastructure errors on *idempotent* reads.
2. **Inside the runtime** (after the tool returns, runtime decides to re-execute). Useful when the error type is consistent across tools.
3. **Let the model retry.** Return the error and let the LLM emit another tool call. Best for *semantic* failures ("no results — try a different query") and validation errors.

The OpenAI Agents SDK default is "the model retries," which is also what Anthropic recommends for tool use generally: "By default, tool errors are passed back to Claude, which can then respond appropriately" ([Tool use with Claude](https://docs.anthropic.com/en/docs/build-with-claude/tool-use/overview)).

**Backoff parameters seen in the wild.** OpenAI's Python cookbook, Anthropic's own examples, and the `tenacity` library converge on roughly the same shape:

- Initial delay 1s, multiplier 2x, max wait 60s, max attempts 5–6.
- Always add jitter: `wait_random_exponential(min=1, max=60)` or `wait_exponential_jitter(initial=1, max=60, jitter=2)` ([tenacity docs](https://tenacity.readthedocs.io/en/latest/api.html)).
- Respect `Retry-After` headers when present (Anthropic, HubSpot, and Tavily all set them on 429).
- Retry on: 5xx, 408, 429, connection errors, timeouts. Don't retry on: 4xx (except 408/429), auth errors, validation errors.

A frequently cited production rule from the Anthropic 429 guide ([SitePoint — Claude API 429 Handling](https://www.sitepoint.com/claude-api-429-error-handling-python/)): "The most effective 429 handling strategy is to avoid the 429 entirely." Proactive throttling + jitter-aware backoff + circuit breaker > naive retry loops.

**When retries are harmful.** Non-idempotent writes. Solar-gen's `push_to_hubspot` is the canonical example: an automatic retry on a 5xx after the request was actually committed creates duplicate Companies/Deals. Three mitigations seen in production:

- **Idempotency keys** (Stripe-style). HubSpot supports `hs_idempotency_key` on some endpoints.
- **No automatic retry; surface the error to the model** with an explicit hint: *"This is a write tool. Do not call it again with the same arguments unless the user confirms."*
- **Check-before-retry**: on suspected partial success, the tool reads back state (e.g., search HubSpot by deal name) before retrying.

The OpenAI Agents SDK community has explicitly debated this — issue [#491](https://github.com/openai/openai-agents-js/issues/491) and [#981](https://github.com/openai/openai-agents-python/issues/981) discuss runaway retry loops on function-calling errors and the need for an *opt-in* retry rather than a default loop.

---

## 3. Error Message Design for the LLM — the highest-leverage lever

This is where Claude Code (the system you are using right now) has set the de-facto standard. The pattern: **diagnose + cite specifics + prescribe**.

### Annotated examples

**Good — Claude Code Edit tool (`old_string` not unique)**
> *"The edit will fail if `old_string` is not unique in the file. Either provide a larger string with more surrounding context to make it unique or use `replace_all` to change every instance of `old_string`."*

Why it works: states the *cause* (not unique), tells the model the *invariant* (must be unique), and gives *two concrete alternatives* (longer context or `replace_all`). The model rarely loops on this because every option to recover is enumerated. Cited from the [Edit tool docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/text-editor-tool) and crash-issue threads ([#3309](https://github.com/anthropics/claude-code/issues/3309)).

**Good — Claude Code "must read before edit" guard**
> *"You must use your `Read` tool at least once in the conversation before editing. This tool will error if you attempt an edit without reading the file."*

Why it works: encoded as a *precondition* in the tool description itself, and re-stated when violated. Pure prevention is cheaper than recovery.

**Good — MCP example from the spec**
> *"Invalid departure date: must be in the future. Current date is 08/08/2025."*

Why it works: surfaces the *constraint* and the *current value the constraint compares against*. The model can fix the input in one step. ([Alpic — better MCP error responses](https://alpic.ai/blog/better-mcp-tool-call-error-responses-ai-recover-gracefully)).

**Good — bash exit code surfacing (Claude Code)**
> *"Command exited with code 127.  `psql: command not found`"*

Why it works: exit code + the actual stderr line. The model can decide whether to install the binary, switch tool, or escalate.

**Bad — LangChain default `str(exception)`**
> *"ConnectionError(MaxRetryError(\"HTTPSConnectionPool(host='api.tavily.com', port=443): Max retries exceeded with url: /search (Caused by ConnectTimeoutError(... ))\"))"*

Why it fails: stack-trace shape, no signal about whether to retry, switch tool, or stop. The model usually responds with another identical call.

**Bad — generic "An error occurred"**
> *"Error: tool failed."*

Why it fails: zero information. The model either retries blindly or gives up.

**Bad — solar-gen current shape (illustrative)**
> *`{"error": "Unexpected error in firecrawl_scrape: HTTPStatusError", "error_category": "tool_error", "detail": "Server error '503 Service Unavailable' for url 'https://api.firecrawl.dev/v1/scrape'"}`*

Why it's mediocre: the category is too generic, no recovery hint, no statement of whether a retry is already in progress, no alternative tool suggested. Compare to the rewrite below in §9.

**Design principles distilled from these:**

1. **Cause + recovery in one sentence.** "X failed because Y; do Z."
2. **Cite the specific value that violated the constraint.** ("departure date 2024-01-01 is in the past — current date is 2026-05-17.")
3. **If there's a sister tool, name it.** ("`web_search` returned no results — try `search_sec_edgar` for SEC-filed projects.")
4. **For non-retriable failures, say so explicitly.** Otherwise the model retries.
5. **For retriable failures the runtime already retried, say so.** "Tavily returned 503 after 3 retries with exponential backoff. Do not call `web_search` again for the next ~30s; try a different tool."

---

## 4. Self-Correction Patterns

The research literature converges on a small set of patterns. The honest summary: **none of them work without external feedback signals.** Pure self-critique is unreliable.

- **Reflexion** (Shinn et al., NeurIPS 2023, [arXiv:2303.11366](https://arxiv.org/abs/2303.11366)). On task failure, the agent generates a verbal post-mortem and stores it in episodic memory; the next attempt prepends the reflection. Works when there is a clear success signal (test passes, env reward). Less applicable to open-ended discovery work.

- **Self-Refine** (Madaan et al., NeurIPS 2023, [arXiv:2303.17651](https://arxiv.org/abs/2303.17651)). One LLM generates, critiques, and revises iteratively — no external tool. Improves outputs ~20% on average across 7 tasks, but the gains are largest where the critique can be grounded (math, code) and smallest in open-ended generation.

- **CRITIC** (Gou et al., 2023, [arXiv:2305.11738](https://arxiv.org/abs/2305.11738)). Key finding: *"LLMs alone cannot reliably carry out critiquing and correction on their own work."* CRITIC succeeds because the critique uses tools (search engines, code execution, fact-checkers). For solar-gen, this argues for *tool-grounded* self-correction (e.g., after a `find_contacts` returns names, verify with a secondary source) rather than asking the model to re-critique its own output.

- **Voyager** (Wang et al., 2023, [arXiv:2305.16291](https://arxiv.org/abs/2305.16291)). Iterative prompting with three feedback channels: environment observations, execution errors, self-verification. The agent retries up to a cap; on success, the code is committed to a skill library. The lesson for solar-gen: when a model finds a working query/sequence (e.g., "for solar EPCs, OSHA + ENR + SEC in this order"), that sequence should be cached/templated rather than re-derived each time.

- **AutoGPT-style "review" step.** Adds a critic call between actions. In practice, in production this is mostly turned off — it doubles cost and the critic frequently rubber-stamps. Use sparingly, for high-stakes irreversible actions only (e.g., HubSpot writes).

**Working subset for solar-gen:**
1. Tool-grounded verification (CRITIC) on critical outputs before persisting.
2. Verbal reflection (Reflexion) injected as a guidance message after N consecutive failures — solar-gen's `EscalationPolicy._is_stagnating` is in this spirit.
3. *No* AutoGPT-style review for read tools; reserve it for the HubSpot push.

---

## 5. Circuit Breakers & Escalation

The literature splits "stop trying" into three triggers:

- **Quantitative** — N consecutive errors, M total errors in a window, or budget exceeded (tokens, dollars, wall-clock). Solar-gen's current `EscalationPolicy.evaluate` covers consecutive errors (`>= 3`) and an iteration cap.
- **Qualitative** — stagnation detection: no new entities/facts surfacing across the last K tool calls. Solar-gen's `_is_stagnating` is a textbook implementation of this.
- **Categorical** — irreversible action requested without confirmation; tool requires human credentials; user policy forbids it. Falls to a hook (pre-tool) rather than a retry counter.

Production patterns from Cognition's writeup ([Devin's 2025 Performance Review](https://cognition.ai/blog/devin-annual-performance-review-2025), [Coding Agents 101](https://devin.ai/agents101)) reinforce: "ask the AI to just flag the most suspicious errors" rather than fix end-to-end. The agent should be biased toward **escalation over silent recovery** when stakes are high. LangGraph's checkpointing supports literal "rewind and ask" — `human-in-the-loop suspension for async approval workflows`.

Solar-gen's `request_guidance` and `request_discovery_review` tools are an exact match for this pattern — they are *escalation as a tool*, which means the model can choose to escalate even before the policy forces it. This is the right design. The gap is that the runtime policy and the model-facing tools don't share vocabulary: the policy uses "escalate_to_user" with a `suggestion` string, while `request_guidance` is the model's name for the same act. Worth aligning.

---

## 6. Tool Sequencing & Preconditions

Three approaches in the wild:

- **Letta tool rules** — declarative graph constraints. `InitToolRule(tool="search_projects")` forces the first tool. `ToolRule(parent="find_contacts", children=["classify_contact"])` chains. `TerminalToolRule(tool="send_message")` ends the run. ([Letta docs](https://docs.letta.com/guides/agents/tool-rules)). Caveat from the docs: most rule types require structured-output models — currently OpenAI gpt-4o family. Doesn't apply directly to Claude tool-use but the *pattern* (declarative constraints) is portable.

- **LangGraph state machines** — preconditions encoded as conditional edges. A "have we read the file?" check is a `state["files_read"]` flag and a routing function. Powerful but verbose ([DEV — Advanced LangGraph](https://dev.to/jamesli/advanced-langgraph-implementing-conditional-edges-and-tool-calling-agents-3pdn)).

- **Claude Code's pre-tool guards** — the cheapest and most legible. The tool description states the precondition ("must Read before Edit"), and a pre-hook enforces it at runtime, returning a clear error if violated. This maps perfectly onto solar-gen's existing `pre_tool` hook interface.

For solar-gen, recommended approach is the Claude Code one — declare preconditions in the tool's `description` field (the model reads it), and enforce them in a `pre_tool` hook (the runtime catches violations). Concretely:

- `push_to_hubspot` precondition: a discovery exists with `review_status='accepted'` for the given `project_id`.
- `save_contact` precondition: the project was confirmed via `approve_discovery`.
- `report_findings` precondition: at least one of `search_*` ran in this turn.

---

## 7. Hallucinated Tool Calls & Invalid Arguments

Two failure modes:

- **Unknown tool name.** The model calls `search_google` when only `web_search` and `brave_search` exist. Solar-gen handles this in `execute_tool` by raising `KeyError(f"Unknown tool: {name}. Available: ...")`. The fact that the available list is included is the right move — the LangChain default is just "tool not found." But raising rather than returning means the error isn't shown to the model unless the runtime catches it.

- **Invalid arguments.** Wrong type, missing required field, extra unrecognized field. Solar-gen does this well: Pydantic `Input` model + `validation_error` returned as a structured dict with `exc.errors()`. The model sees the field name and validation message and almost always fixes it in one step. The OpenAI Agents SDK does the same — its `ModelBehaviorError` retry policy is largely about validation-error retries ([Issue #325](https://github.com/openai/openai-agents-python/issues/325)).

The pattern across frameworks: **JSON-schema validation + return the validation error verbatim**. Do not paraphrase. The model's mental model of its own JSON output is precise enough that the exact Pydantic/JSON-Schema message resolves the issue. The one improvement worth making: include a tiny example of valid input in the error string, especially for tools with complex shapes (e.g., nested objects in `push_to_hubspot`).

---

## 8. Partial Failures

The cleanest production model is **MCP's `isError` boolean on `CallToolResult`** ([MCP spec](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)): the tool *always* returns successfully at the protocol level; whether the result is "good," "good with caveats," or "failed" is encoded in the payload.

Three sub-cases:

1. **Full success.** `{ok: true, data: {...}}`.
2. **Partial success / caveats.** `{ok: true, data: {...}, warnings: ["could not parse phone field for contact 2/5"]}`. The model gets the usable data *and* sees the caveat. This is what solar-gen's scrape/enrich tools should do — currently, on one parser failure they often fall to the `Exception` branch and return only an `error`, losing the partial yield.
3. **Hard failure.** `{ok: false, error: "...", error_category: "...", retriable: false}`.

Cognition's writeup ([Devin Sonnet 4.5 lessons](https://cognition.ai/blog/devin-sonnet-4-5-lessons-and-challenges)) makes a related point: returning *too much* error context blows up the context window and the model loses focus. Keep partial-result envelopes small.

---

## 9. Recommendations for solar-gen

### A. `runtime/escalation.py`

1. **Distinguish error categories in the policy, not just count them.** Currently `_count_consecutive_errors` treats every `{"error": ...}` equally. Three failed `web_search` calls (transient) are different from one failed `push_to_hubspot` (irreversible action attempted) followed by two `validation_error`s. Suggested change: read `error_category` and weight irreversibles higher (escalate after 1, not 3).

2. **Align with `request_guidance`.** The `EscalationPolicy.evaluate` action `escalate_to_user` and the `request_guidance` tool are the same idea. Either (a) inject a guidance message that says "consider calling `request_guidance`" and let the model decide, or (b) emit `request_guidance` synthetically. Today they're parallel paths the model has to reconcile.

3. **Add a "no-retry" signal for non-idempotent failures.** When a tool returns `{retriable: false, idempotent: false}`, the policy should *immediately* escalate rather than wait for 3 consecutive errors.

4. **Cap reflection growth.** `_seen_signals` already caps at 500 — good. The `Counter`-based `_summarize_tool_usage` is fine but doesn't separate errors from successes. Worth showing the user "web_search x12 (3 errors), push_to_hubspot x1 (1 error)" so the suggestion is grounded.

### B. Tool base class (`tools/_base.py`)

Today `_base.py` is just cache helpers + `ToolDef`. Promote it to a proper tool contract:

```python
class ToolResult(TypedDict, total=False):
    ok: bool                       # required
    data: Any                      # on success
    warnings: list[str]            # partial success
    error: str                     # on failure — human + model-readable sentence
    error_category: Literal[
        "validation_error", "auth_error", "rate_limit",
        "transient", "permanent", "no_results", "precondition_failed",
    ]
    retriable: bool                # default depends on category
    idempotent: bool               # default False for writes
    next_actions: list[str]        # 0–3 concrete suggestions, names of tools or args to try
```

And a standard error-string builder:

```python
def format_error(
    *, cause: str, recovery: list[str], retried: int = 0, category: str
) -> str:
    """Render an error string the model can act on.
    Format: "<cause>. <retry status>. Try: <recovery 1> | <recovery 2>."
    """
```

Then audit every tool to use it. Example rewrites:

| Tool | Current | Improved |
|------|---------|----------|
| `web_search` (empty) | `{"error": "Empty search query."}` | `{"ok": false, "error": "Empty query — web_search requires at least 3 characters.", "error_category": "validation_error", "next_actions": ["call web_search with a non-empty query containing the EPC name and state"]}` |
| `firecrawl_scrape` (503 after retries) | `{"error": "Unexpected error in firecrawl_scrape: HTTPStatusError", ...}` | `{"ok": false, "error": "Firecrawl returned 503 after 3 retries with exponential backoff. The service appears down. Do not retry firecrawl_scrape in this turn.", "error_category": "transient", "retriable": false, "next_actions": ["fetch_page (raw HTTP, no JS rendering)", "search_spw for a cached snippet"]}` |
| `push_to_hubspot` (missing token) | `{"error": "HubSpot is not connected. Ask the user..."}` | `{"ok": false, "error": "HubSpot is not connected — no API token in Settings. This is a user-action error, not a transient one.", "error_category": "auth_error", "retriable": false, "idempotent": false, "next_actions": ["call request_guidance asking the user to configure HubSpot"]}` |
| `find_contacts` (no results) | `{"error": "No contacts found"}` (currently) | `{"ok": true, "data": {"contacts": []}, "warnings": ["No contacts found for this EPC across LinkedIn, Exa, HubSpot. This is not an error — the EPC may be small or recently formed."], "next_actions": ["scrape_epc_website for an About/Team page", "search_sec_edgar for officer filings"]}` *(note: "no results" is success-with-empty, not failure)* |
| `enrich_contact_email` (partial) | currently throws if one of N fails | `{"ok": true, "data": {"emails": [...]}, "warnings": ["3 of 5 contacts enriched; 2 had no matching domain"]}` |

### C. Tool preconditions

Add a `precheck(tool_input, context) -> str | None` method to the tool module contract. If it returns a string, the runtime returns that as the tool's error result *without* calling the tool. Use for:

- `push_to_hubspot` — verify an accepted discovery exists.
- `save_contact` — verify the project is approved.
- Any tool that depends on prior state.

The pre-hook plumbing already exists (`run_pre_hooks`); this is just a convention for tools to expose their preconditions declaratively.

### D. Retry policy

Adopt `tenacity` consistently (already used in `web_search.py` for Tavily, with `_MAX_RETRIES = 2`). House rules:

- **Read tools** (`web_search`, `fetch_page`, `search_*`): up to 3 retries, `wait_random_exponential(min=1, max=30)`, retry on 5xx/408/429/timeout, never retry on 4xx-except-429.
- **Write tools** (`push_to_hubspot`, `save_contact`): **no automatic retries.** Return the error to the model with `retriable: false, idempotent: false`. If the user wants to retry, they say so.
- **Honor `Retry-After`** when present.
- Surface "we already retried N times" in the error string to the model so it doesn't redundantly retry on its own.

### E. Hallucinated tool calls

Today `execute_tool` raises `KeyError` on unknown tool — this propagates up and may crash the loop. Change to: catch and return `{"ok": false, "error": "Unknown tool '<name>'. Available tools: <list>.", "error_category": "validation_error"}`. The model will almost always pick the right one on the second try.

### F. Don't double-surface errors

`ToolHealthHook` and `EscalationPolicy._count_consecutive_errors` both count consecutive errors and inject guidance. Pick one. Recommend keeping the policy (it has more context) and removing the `_guidance` injection from the hook to avoid duplicate nags in the model's context.

---

## Sources

- LangChain — [How to handle tool errors](https://python.langchain.com/docs/how_to/tools_error/), [`ToolException` API](https://python.langchain.com/api_reference/core/tools/langchain_core.tools.base.ToolException.html), [Self-Correcting Chain (Medium)](https://medium.com/@kbdhunga/self-correcting-chain-managing-tool-failures-in-langchain-f954fda01d87)
- OpenAI Agents SDK — [Error Recovery Patterns (DeepWiki)](https://deepwiki.com/openai/openai-agents-python/14.2-multi-agent-orchestration-examples), [Agent reference](https://openai.github.io/openai-agents-python/ref/agent/), [Issue #325 ModelBehaviorError retry](https://github.com/openai/openai-agents-python/issues/325), [Issue #491 tool call retry](https://github.com/openai/openai-agents-js/issues/491)
- Letta — [Creating Tool Rules](https://docs.letta.com/guides/agents/tool-rules)
- smolagents — [agents.py source](https://github.com/huggingface/smolagents/blob/main/src/smolagents/agents.py), [Building good Smolagents](https://smolagents.org/docs/building-good-smolagents/)
- Anthropic — [Tool use with Claude](https://docs.anthropic.com/en/docs/build-with-claude/tool-use/overview), [Text editor tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/text-editor-tool), [Error reference (Claude Code)](https://code.claude.com/docs/en/errors), [Implement tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/implement-tool-use), [Claude API 429 handling (SitePoint)](https://www.sitepoint.com/claude-api-429-error-handling-python/)
- MCP — [Tools (spec 2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25/server/tools), [Tools concepts](https://modelcontextprotocol.info/docs/concepts/tools/), [Better MCP tool call error responses (Alpic)](https://alpic.ai/blog/better-mcp-tool-call-error-responses-ai-recover-gracefully), [MCP Error Codes (mcpevals)](https://www.mcpevals.io/blog/mcp-error-codes)
- Papers — [Reflexion (Shinn et al., 2023)](https://arxiv.org/abs/2303.11366), [Self-Refine (Madaan et al., 2023)](https://arxiv.org/abs/2303.17651), [CRITIC (Gou et al., 2023)](https://arxiv.org/abs/2305.11738), [Voyager (Wang et al., 2023)](https://arxiv.org/abs/2305.16291)
- Production writeups — [Cognition: Devin's 2025 Performance Review](https://cognition.ai/blog/devin-annual-performance-review-2025), [Cognition: Devin Sonnet 4.5 Lessons](https://cognition.ai/blog/devin-sonnet-4-5-lessons-and-challenges), [Coding Agents 101](https://devin.ai/agents101), [Inside Claude Code architecture](https://www.penligent.ai/hackinglabs/inside-claude-code-the-architecture-behind-tools-memory-hooks-and-mcp/)
- Retry libraries — [tenacity docs](https://tenacity.readthedocs.io/), [tenacity API](https://tenacity.readthedocs.io/en/latest/api.html)
- LangGraph — [Advanced LangGraph: Conditional Edges](https://dev.to/jamesli/advanced-langgraph-implementing-conditional-edges-and-tool-calling-agents-3pdn), [Workflows and agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
