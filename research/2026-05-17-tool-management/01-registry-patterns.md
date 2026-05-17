# Tool Registry, Loading, and Scoping Across Agent Frameworks

_Research date: 2026-05-17. Scope: how popular open-source agent frameworks structure their tool registry, tool loading, and tool scoping. Goal: extract production patterns that solar-gen can learn from before refactoring our ~40-tool stack._

---

## 0. Plain English

Most agent frameworks are converging on the same shape: a tool is a typed Python function, the **registry is per-agent** (sometimes layered globally), and the framework lets you **filter or namespace** what each agent or sub-agent sees. The hard problem the field is now actively solving is the "too many tools" problem — once you cross ~30–50 tools, model accuracy drops sharply, so the leading frameworks now load **only a subset of tool schemas into the prompt** and let the model search the rest on demand. Anthropic's Tool Search Tool (`defer_loading: true`) and LangChain's `langgraph-bigtool` are the clearest examples. MCP is the lingua franca for cross-framework tool servers, and dynamic tool discovery (`listChanged` + `tools/list`) is now part of the spec.

---

## 1. Anthropic Claude Agent SDK & Claude Code

### Tool definition

In the Python SDK, tools are functions decorated with `@tool(name, description, schema_dict)` and then packaged into an **in-process MCP server** via `create_sdk_mcp_server`:

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool("greet", "Greet a user", {"name": str})
async def greet_user(args):
    return {"content": [{"type": "text", "text": f"Hello, {args['name']}!"}]}

server = create_sdk_mcp_server(name="my-tools", version="1.0.0", tools=[greet_user])
```

Source: [claude-agent-sdk-python README](https://github.com/anthropics/claude-agent-sdk-python).

### Registry model

There is no global registry. The runtime is configured per session via `ClaudeAgentOptions`, which takes a `mcp_servers={}` map (mixing in-process SDK servers and external stdio/HTTP servers) and an `allowed_tools=[]` list. Built-in tools (`Read`, `Write`, `Bash`, `Grep`, `Glob`, `WebFetch`, `WebSearch`, `AskUserQuestion`, etc.) are always discoverable; `allowed_tools` is a **permission allowlist**, not a visibility filter — unlisted tools fall through to `permission_mode` / `can_use_tool` callbacks for approval (per the README explainer).

MCP tools are namespaced as `mcp__<server>__<tool>` (the IDs you see in `allowed_tools`).

### Sub-agent scoping

Sub-agents in Claude Code (`.claude/agents/*.md` or via the SDK's `AgentDefinition`) have an **independent tool subset** defined in YAML frontmatter:

```markdown
---
name: code-reviewer
description: Reviews code for quality and best practices
tools: Read, Glob, Grep
disallowedTools: Write, Edit
model: sonnet
permissionMode: default
mcpServers: [slack]
skills: [security-review]
---
You are a code reviewer...
```

If `tools` is omitted the subagent **inherits** the parent's toolset; `disallowedTools` subtracts from it. Plugin subagents ignore `mcpServers`/`hooks`/`permissionMode` for safety. Source: [code.claude.com docs — Create custom subagents](https://code.claude.com/docs/en/sub-agents).

Built-in subagents (Explore, Plan, general-purpose) ship with hard tool restrictions — Explore is "read-only tools (denied access to Write and Edit)" with Haiku — illustrating Anthropic's preferred pattern: **specialize a subagent by both model tier and toolset**.

### Skills vs tools

Skills are a separate, complementary primitive. A skill is a Markdown file at `.claude/skills/*/SKILL.md` that the agent invokes via the `Skill` tool, which loads the skill's instructions and (optionally) brings additional bundled scripts/tools into scope. Subagents can `skills: [...]` to **preload** a skill's full content at startup, but can still invoke unlisted skills at runtime. So: skills are lazy, contextual instruction-and-tool bundles; tools are the atomic capability.

### Deferred / on-demand schema loading (the ToolSearch pattern)

This is the most important Anthropic-specific pattern for our purposes. The raw Messages API now supports `defer_loading: true` on any tool definition, combined with a built-in **Tool Search Tool** (`tool_search_tool_regex_20251119` or `tool_search_tool_bm25_20251119`). Source: [Tool search tool docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool).

Mechanics:

1. You send all tool definitions in the request, but mark most with `defer_loading: true`.
2. Deferred tools are **stripped from the system-prompt prefix** (preserving prompt-cache hits).
3. Claude only sees the search tool plus your 3–5 hot tools.
4. When it needs more, it calls the search tool with a regex or natural-language query; the API returns 3–5 `tool_reference` blocks.
5. The API auto-expands those references into full schemas inline in the conversation before showing them to Claude.

Reported impact (from Anthropic's docs): 85% fewer tool-definition tokens, Opus 4 MCP eval accuracy 49% → 74%, Opus 4.5 79.5% → 88.1%. Max catalog 10,000 tools.

Claude Code itself now uses this internally — the `ToolSearch` tool you see in this very session, plus the `<function>...</function>` re-inflation pattern, is exactly the deferred-tool flow. (See open SDK issues [#525 Python](https://github.com/anthropics/claude-agent-sdk-python/issues/525) and [#124 TypeScript](https://github.com/anthropics/claude-agent-sdk-typescript/issues/124) — surfacing `defer_loading` to SDK users is still in progress, but Claude Code internally uses it.)

You can also implement client-side tool search by returning `tool_reference` content blocks from any custom tool — Anthropic publishes a [cookbook with embeddings](https://platform.claude.com/cookbooks/tool_use).

### Anthropic's written recommendations

From [Writing effective tools for AI agents](https://www.anthropic.com/engineering/writing-tools-for-agents): five principles — (1) pick high-leverage tools, not API wrappers, (2) **namespace** tools (`github_`, `slack_` prefixes), (3) return human-readable context, not raw IDs, (4) implement pagination/filtering/truncation with sane defaults (keep responses < 25k tokens), (5) prompt-engineer descriptions; agent-driven iteration ("Claude optimizes its own tools against an eval") yields the biggest wins.

---

## 2. OpenAI Agents SDK / Swarm

### Tool definition (Agents SDK)

```python
from agents import function_tool

@function_tool
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return ...
```

Under the hood this produces a `FunctionTool` dataclass with `name`, `description`, `params_json_schema`, `on_invoke_tool`, plus per-tool knobs: `is_enabled` (dynamic predicate against `RunContext`), `needs_approval`, `timeout_seconds`/`timeout_behavior`, `tool_input_guardrails`/`tool_output_guardrails`, `strict_json_schema`. Source: [openai-agents-python tool.py](https://github.com/openai/openai-agents-python/blob/main/src/agents/tool.py).

### Registry model

Per-agent, attached at construction:

```python
agent = Agent(name="…", instructions="…", tools=[get_weather, ...])
```

`Agent.get_all_tools()` resolves enabled tools dynamically each turn by awaiting each tool's `is_enabled` predicate. So scoping is **two-layer**: static `tools=` list plus dynamic gating by `is_enabled(ctx)`. Source: [agent.py](https://github.com/openai/openai-agents-python/blob/main/src/agents/agent.py).

### Sub-agents = handoffs

```python
agent = Agent(tools=[...], handoffs=[sales_agent, support_agent])
```

Handoffs are first-class — when Claude/GPT picks a handoff, control transfers to that sub-agent (with its own `tools`), and the parent's tools disappear from context. This is the same pattern as Swarm: ["An Agent can hand off to another Agent by returning it in a function"](https://github.com/openai/swarm). There is no shared tool universe; each agent's tool list is its own.

### tool_use_behavior

Controls how tool outputs flow back: `"run_llm_again"` (default), `"stop_on_first_tool"`, `StopAtTools(names=[...])`, or a custom callable. Useful for deterministic short-circuits.

---

## 3. LangChain + LangGraph

### Tool definition

Two paths:

```python
# Decorator — schema inferred from type hints + docstring
from langchain_core.tools import tool

@tool
def multiply(a: int, b: int) -> int:
    """Multiply two integers."""
    return a * b

# Class — full control
from langchain_core.tools import BaseTool
class Search(BaseTool):
    name = "search"
    description = "..."
    args_schema = MySearchArgs  # Pydantic
    handle_tool_error = True    # or a callable returning str
    def _run(self, query: str): ...
```

`StructuredTool` is the multi-arg variant; `args_schema` lets you supply a Pydantic model explicitly. Source: [langchain_core.tools.StructuredTool](https://api.python.langchain.com/en/latest/core/tools/langchain_core.tools.structured.StructuredTool.html).

### Error handling

`handle_tool_error` (bool | str | Callable[[ToolException], str]) catches `ToolException` and returns a string to feed back to the LLM — critical for resilient agents. There's also `handle_validation_error` for arg-schema failures.

### Registry model

There is no global registry. Tools are bound to the LLM via `llm.bind_tools([...])`, or wrapped in a LangGraph `ToolNode`:

```python
from langgraph.prebuilt import ToolNode, create_react_agent
agent = create_react_agent(model, tools=[search, multiply])
```

`ToolNode` parses `tool_calls` off the AIMessage, dispatches in parallel, and appends `ToolMessage` results to state. `create_react_agent` (now superseded by `create_agent` in the `langchain` package, per [LangChain docs](https://reference.langchain.com/python/langgraph.prebuilt/chat_agent_executor/create_react_agent)) wires this into a default ReAct loop.

### Per-agent / per-graph scoping

LangGraph composition is graph-level: each node can wrap its own model+tools, and you route between them via edges. There is no inherent "subagent" primitive — you build it from nodes.

### Large-toolset solution: `langgraph-bigtool`

The directly-relevant pattern: [langchain-ai/langgraph-bigtool](https://github.com/langchain-ai/langgraph-bigtool) puts every tool in a vector store keyed by description, exposes a single `retrieve_tools` meta-tool, and the agent searches the registry before calling.

```python
store = InMemoryStore(index={"embed": embeddings, "dims": 1536, "fields": ["description"]})
for tool_id, tool in tool_registry.items():
    store.put(("tools",), tool_id, {"description": f"{tool.name}: {tool.description}"})

def retrieve_tools(query: str, *, store: BaseStore) -> list[str]:
    return [r.key for r in store.search(("tools",), query=query, limit=2)]

builder = create_agent(llm, tool_registry, retrieve_tools_function=retrieve_tools)
```

This is the open-source mirror of Anthropic's Tool Search Tool, with the embedding/index living in your process.

---

## 4. smolagents (HuggingFace)

### Tool definition

Either subclass `Tool` (preferred for complex cases) or decorate:

```python
from smolagents import Tool, tool

class WeatherTool(Tool):
    name = "weather"
    description = "Get weather for a city"
    inputs = {"city": {"type": "string", "description": "City name"}}
    output_type = "string"
    def forward(self, city: str) -> str: ...

@tool
def add_numbers(a: int, b: int) -> int:
    """Add two integers."""
    return a + b
```

Source: [smolagents tools tutorial](https://github.com/huggingface/smolagents/blob/main/docs/source/en/tutorials/tools.md).

### Registry model

Tools are passed as a list to the agent constructor; internally the agent stores them as a dict keyed by name (`agent.tools[name] = tool`), so you can hot-add tools at runtime.

### Tool collections

`ToolCollection` is the multi-tool import primitive:

```python
from smolagents import ToolCollection, CodeAgent
with ToolCollection.from_mcp(server_params, trust_remote_code=True) as tc:
    agent = CodeAgent(tools=[*tc.tools], model=model)
ToolCollection.from_hub("huggingface-tools/diffusion-tools")
```

Also: `Tool.from_langchain()`, `Tool.from_space()` (Gradio), `Tool.from_gradio()`. Cross-framework interop is a primary design goal.

### Code-agent vs tool-calling

`CodeAgent` writes Python code that **calls tools as ordinary functions**; `ToolCallingAgent` uses JSON tool calls. The CodeAgent path reportedly takes "30% fewer steps" — composition (loops, conditionals, intermediate variables) happens in code, not in another model turn. Tools execute in a sandbox: `LocalPythonExecutor` (best-effort), `E2B`, `Modal`, `Docker`, or `Pyodide`.

### Sub-agents

`managed_agents=[...]` makes a sub-agent callable as a tool — same shape as OpenAI's "agents as tools."

---

## 5. AutoGen, CrewAI, Letta, PydanticAI

### AutoGen

Tools are plain Python functions registered against a pair of `ConversableAgent`s — one as **caller** (LLM that proposes the call), one as **executor** (runs it):

```python
from autogen import register_function
register_function(
    my_function,
    caller=assistant_agent,
    executor=user_proxy_agent,
    name="my_function",
    description="..."
)
```

This split is unique to AutoGen — most other frameworks fuse the two roles. Tool config can be filtered by tags via `filter_dict`. Source: [AutoGen 0.2 tool-use tutorial](https://microsoft.github.io/autogen/0.2/docs/tutorial/tool-use/).

### CrewAI

Two patterns — `@tool("Name")` decorator for simple functions, or subclass `BaseTool` with `name`, `description`, `args_schema` (Pydantic), and `_run()`. Tools attach to either an **agent** (`Agent(tools=[...])`) or a **task** (`Task(tools=[...])`) — task-level tools override agent-level for that step. Source: [crewAI tools docs](https://docs.crewai.com/en/concepts/tools).

### Letta (MemGPT)

Letta is the outlier — and the most relevant for solar-gen because its agents are long-running and **stateful in a database**. Key differences:

- **Persistent tool registry.** Tools live in a server-side library and are attached to agents by ID. `agents.create(tool_ids=[...])` and `agents.modify(...)` are SDK calls; detaching a tool leaves it in the library for reuse. Source: [Connecting agents to tools](https://docs.letta.com/agents/tools).
- **External library auto-loading.** Letta v0.5.1+ can bulk-import Composio, LangChain, and CrewAI tools into the server registry.
- **Tool rules** — a graph-style DSL constraining which tools can fire when. Examples:
  - `TerminalToolRule(tool_name=...)` — calling this tool ends the step.
  - `InitToolRule(tool_name=...)` — must be called first.
  - `ChildToolRule(tool_name=A, children=[B, C])` — after A, only B or C are allowed.
  - `ConditionalToolRule(...)` — branch by return value.
  - `MaxCountPerStepToolRule(tool_name=..., max_count_limit=N)` — rate-limit a tool inside one step.
  
  Source: [Tool rules guide](https://docs.letta.com/guides/agents/tool-rules). This is the closest open-source analog to Claude Code's per-subagent hooks + tool restrictions, but applied at the **tool-graph** level rather than the agent-definition level.

### PydanticAI

PydanticAI has the cleanest abstraction over "many toolsets, composed":

```python
from pydantic_ai import Agent, FunctionToolset, CombinedToolset

weather = FunctionToolset(tools=[get_weather, get_forecast])
db = FunctionToolset(tools=[query_db])

agent = Agent('openai:gpt-5.2', toolsets=[
    CombinedToolset([weather, db]),
    db.prefixed('db'),           # PrefixedToolset → tools become db_query_db
    weather.filtered(lambda ctx, td: 'imperial' not in td.name),  # FilteredToolset
])
```

Source: [Toolsets docs](https://ai.pydantic.dev/toolsets/). The composable primitives are:

- `FunctionToolset` — wrap functions
- `CombinedToolset` — union
- `PrefixedToolset` — namespace
- `FilteredToolset` — predicate filter (per-run dynamic)
- `WrapperToolset` — subclass to intercept `call_tool` (logging, retry, etc.)
- `DeferredToolset` — explicit support for the defer_loading pattern

`@agent.toolset` with `per_run_step=False` registers a **dynamic factory** that builds the toolset from `RunContext` each run (or once per run if `per_run_step=False`). And `prepare_tools` lets you mutate `tool_defs` before each step — e.g., hide tools based on user permissions, agent state, or step count.

This is probably the most ergonomic Python API in the field for the patterns we care about.

---

## 6. MCP (Model Context Protocol)

The shared substrate that nearly every framework above now speaks. Source: [MCP spec 2025-06-18 — Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools).

### Tool advertisement

Each server declares a `tools` capability, optionally with `listChanged: true`. Clients call `tools/list` (paginated via `cursor`/`nextCursor`) to discover:

```json
{
  "name": "get_weather",
  "title": "Weather Information Provider",
  "description": "Get current weather information for a location",
  "inputSchema": {
    "type": "object",
    "properties": {"location": {"type": "string"}},
    "required": ["location"]
  },
  "outputSchema": { ... },     // optional, since 2025-06
  "annotations": { ... }        // readOnlyHint, destructiveHint, idempotentHint, openWorldHint
}
```

### Tool invocation

`tools/call` with `{name, arguments}` returns a `content` array of text/image/audio/resource_link blocks plus an `isError` flag.

### Dynamic discovery

When tools change mid-session, servers send `notifications/tools/list_changed`; clients re-fetch. This is what lets Letta/Claude Code/etc. hot-reload plugin or skill tools without restarting the agent.

### Client-side filtering

The spec is silent on filtering — that's a client concern. In practice every framework adds its own filter layer on top of MCP's catalog (Claude Code's `allowed_tools`, PydanticAI's `FilteredToolset`, smolagents' explicit list, etc.). MCP gives you the catalog; the framework picks the subset.

---

## Converging patterns vs idiosyncrasies

### Converging (the field is settling here)

1. **Tools are typed Python functions** — decorator + introspection. JSON Schema is always derivable. Pydantic for arg validation is now table stakes (LangChain, CrewAI, PydanticAI, smolagents-class-form).
2. **Per-agent tool lists**, not a global registry. Even when there's a server-side library (Letta) or vector store (langgraph-bigtool), the active per-turn toolset is a filtered slice. Global registries are anti-pattern.
3. **Namespacing by prefix**. `mcp__<server>__<tool>` in Anthropic, `PrefixedToolset` in PydanticAI, prefix conventions in Anthropic's writing-tools guide (`github_`, `slack_`).
4. **Sub-agent specialization** = own system prompt + own tool subset + often a smaller/cheaper model. Universal across Claude Code subagents, OpenAI handoffs, smolagents managed_agents, CrewAI agents, AutoGen group chat.
5. **Dynamic per-call filtering**. `is_enabled(ctx)` (OpenAI), `prepare_tools` (PydanticAI), `FilteredToolset`, `tool_rules` (Letta). Tools blink in and out per turn based on state.
6. **MCP as the wire format**. Even closed ecosystems now speak MCP — it's how heterogeneous tools cross framework boundaries.

### Where the field is heading (and Anthropic specifically recommends)

- **RAG-over-tools / deferred schema loading** is the consensus answer to "too many tools." Anthropic ships it server-side as Tool Search Tool with `defer_loading: true`; LangChain ships it client-side as `langgraph-bigtool`; PydanticAI exposes a `DeferredToolset` primitive; the [RAG-MCP paper (arXiv 2505.03275)](https://arxiv.org/html/2505.03275v1) shows >3× tool-selection accuracy and >50% prompt-token reduction. Berkeley FCL data shows accuracy collapsing 43% → 2% as tool count grows 4 → 51 — so this isn't optional past ~30 tools.
- **Prompt-cache-preserving design**. Anthropic's `defer_loading` is specifically engineered to keep deferred tools out of the prefix so caching is preserved. Any solar-gen design should treat the tool prefix as a cache anchor.
- **Tool description as the lever**. Anthropic's "Writing effective tools" emphasizes that description-tuning yields outsized wins; even better, use Claude to optimize its own tool descriptions against an eval.

### Idiosyncratic but interesting

- **AutoGen's caller/executor split** — useful when you want a humans-in-the-loop boundary, but most frameworks don't bother.
- **Letta's tool rules graph** — a real declarative state machine over tool calls. The closest production analog to what hooks/escalation give solar-gen, but persisted.
- **smolagents CodeAgent** — tools as Python functions called inside generated code, not as JSON tool calls. Anthropic's "Programmatic Tool Calling" is conceptually similar.
- **Claude Code's skills as lazy tool-bundles** — a layer above tools that lets you ship "specialty kits" (e.g., `security-review`) that only enter context when needed.

---

## Patterns worth stealing for solar-gen

- **Adopt deferred loading now.** With ~40 tools we're already past the accuracy cliff. Send `defer_loading: true` on everything except 4–6 always-hot tools (likely `Read`, `Grep`, `Glob`, plus the 2–3 core solar-gen actions), and let Claude search the rest via the Tool Search Tool. The current ToolSearch behavior in Claude Code is exactly this pattern; mirror it for our SDK runtime.
- **Namespace aggressively.** Pick prefixes per domain — `iso_`, `ferc_`, `permit_`, `scraper_`, `db_` — so both humans and the search tool can discover by group. Matches Anthropic's explicit advice.
- **Treat sub-agents like Claude Code subagents**: each specialized sub-agent gets `(system_prompt, tools, model, permission_mode, hooks, skills)` as a single bundle. Make this a typed dataclass (`AgentDefinition`-style) rather than ad-hoc config. The YAML/Markdown frontmatter pattern (`.claude/agents/*.md`) is checkable into git and survives refactors well.
- **Layer the registry**: (1) a server-side **persistent tool catalog** (Letta-style — every tool registered once with metadata + tags), (2) a per-agent **manifest** that selects/filters/prefixes from the catalog, (3) a per-turn **dynamic filter** for state-dependent visibility (PydanticAI's `prepare_tools` shape). Keep these strictly separated.
- **Build a `FilteredToolset` / `prepare_tools` equivalent.** A single `tool_filter(ctx, tool_defs) -> tool_defs` callback that the runtime invokes each step gives us escalation, permissions, and compaction-aware tool gating in one place.
- **Use tags + retrieval, not lists, for tool selection.** Once we exceed ~30 tools, switch from explicit `allowed_tools=[...]` lists to (a) tag-based pre-filter (`tags={"scraping","public"}`), (b) embedding retrieval over descriptions (like `langgraph-bigtool`), surfaced as a custom tool that returns `tool_reference` blocks per the Anthropic cookbook.
- **Treat tool descriptions as first-class artifacts.** Version them, eval them, and let Claude itself iterate on them (Anthropic's prototype-evaluate-collaborate loop). Aim for responses < 25k tokens with pagination on everything that could blow up (DB queries, scraper output, FERC filings).
- **Tool rules for safety-critical flows.** Where we have invariants ("never call `write_db` without a prior `validate_filing` in the same step"), Letta's `ChildToolRule` / `MaxCountPerStepToolRule` shape is cleaner than hooks. We could implement this as a pre-call validator that consults a small graph of constraints.
- **Make MCP the boundary.** Wrap every external integration as an MCP server (even if in-process via the SDK's `create_sdk_mcp_server`) so we get listChanged, schema-only loading, and trivial cross-framework portability for free.

---

## Source index

- Claude Agent SDK Python: https://github.com/anthropics/claude-agent-sdk-python
- Claude Agent SDK overview: https://code.claude.com/docs/en/agent-sdk/overview
- Claude Code sub-agents: https://code.claude.com/docs/en/sub-agents
- Anthropic Tool Search Tool: https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool
- Anthropic Advanced tool use: https://www.anthropic.com/engineering/advanced-tool-use
- Anthropic Writing effective tools: https://www.anthropic.com/engineering/writing-tools-for-agents
- Anthropic Effective context engineering: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- OpenAI Agents Python tool.py: https://github.com/openai/openai-agents-python/blob/main/src/agents/tool.py
- OpenAI Agents Python agent.py: https://github.com/openai/openai-agents-python/blob/main/src/agents/agent.py
- OpenAI Swarm: https://github.com/openai/swarm
- LangChain StructuredTool: https://api.python.langchain.com/en/latest/core/tools/langchain_core.tools.structured.StructuredTool.html
- LangGraph create_react_agent: https://reference.langchain.com/python/langgraph.prebuilt/chat_agent_executor/create_react_agent
- langgraph-bigtool: https://github.com/langchain-ai/langgraph-bigtool
- smolagents tools tutorial: https://github.com/huggingface/smolagents/blob/main/docs/source/en/tutorials/tools.md
- AutoGen tool use: https://microsoft.github.io/autogen/0.2/docs/tutorial/tool-use/
- CrewAI tools: https://docs.crewai.com/en/concepts/tools
- Letta agents/tools: https://docs.letta.com/agents/tools
- Letta tool rules: https://docs.letta.com/guides/agents/tool-rules
- PydanticAI toolsets: https://ai.pydantic.dev/toolsets/
- MCP tools spec: https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- RAG-MCP paper: https://arxiv.org/html/2505.03275v1
