"""Chat agent: Claude with tools for project search and EPC discovery.

Streams responses as SSE events using the Vercel AI SDK protocol so
the React frontend can render text + interactive tool-result components.

Architecture note: The chat agent delegates EPC research to the separate
research agent (agent.py) rather than doing web search directly. This is
intentional — keeps context windows focused and avoids polluting chat
history with 30-40k tokens of web search results per research run.
Revisit this if latency or cost becomes an issue.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import AsyncGenerator

import anthropic

from . import db
from .agent import run_agent_async
from .batch import run_batch
from .knowledge_base import build_knowledge_context, query_knowledge_base
from .sse import StreamWriter

MODEL = "claude-sonnet-4-20250514"
MAX_TOOL_ROUNDS = 5

SYSTEM_PROMPT = """\
You are an AI assistant that helps users explore solar energy projects and \
discover EPC (Engineering, Procurement & Construction) contractors.

You have tools to:
- Search the project database by state, region, capacity, developer, etc.
- Research a single project to identify its EPC contractor (web research)
- Batch-research multiple projects at once
- Look up existing EPC discoveries
- Query the knowledge base for developer/EPC profiles and relationships

Be concise and helpful. When showing search results, briefly summarize what \
you found. When a user asks to research projects, use the research tools. \
Always explain what you're doing before calling a tool.

States in the database are stored as two-letter abbreviations (TX, CA, IL, etc.). \
Always use abbreviations when filtering by state.

When referencing projects, include their name, developer, MW capacity, and state.

Project searches are scoped to expected COD 2025–2028 by default. Projects outside \
this window are likely already constructed or too far out. If a user explicitly asks \
about projects outside this range, override the cod_min/cod_max filters.
"""

TOOLS = [
    {
        "name": "search_projects",
        "description": (
            "Search the solar project database. Returns projects matching "
            "the given filters, sorted by capacity (largest first). "
            "Use this when users ask to find, show, or list projects."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "state": {
                    "type": "string",
                    "description": "State abbreviation or name (e.g. 'TX', 'Texas').",
                },
                "iso_region": {
                    "type": "string",
                    "description": "ISO region: ERCOT, CAISO, or MISO.",
                },
                "mw_min": {
                    "type": "number",
                    "description": "Minimum MW capacity.",
                },
                "mw_max": {
                    "type": "number",
                    "description": "Maximum MW capacity.",
                },
                "developer": {
                    "type": "string",
                    "description": "Developer name (partial match).",
                },
                "fuel_type": {
                    "type": "string",
                    "description": "Fuel type, e.g. 'Solar', 'Wind', 'Battery'.",
                },
                "needs_research": {
                    "type": "boolean",
                    "description": "If true, only projects without an EPC contractor.",
                },
                "has_epc": {
                    "type": "boolean",
                    "description": "If true, only projects with a known EPC.",
                },
                "search": {
                    "type": "string",
                    "description": "Free text search across project name, developer, queue ID.",
                },
                "cod_min": {
                    "type": "string",
                    "description": "Earliest expected COD (YYYY-MM-DD). Default '2025-01-01'. Set to null to remove lower bound.",
                },
                "cod_max": {
                    "type": "string",
                    "description": "Latest expected COD (YYYY-MM-DD). Default '2028-12-31'. Set to null to remove upper bound.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 20).",
                },
            },
        },
    },
    {
        "name": "research_epc",
        "description": (
            "Research a single project to discover its EPC contractor. "
            "This runs a web research agent that searches multiple sources. "
            "Use when a user asks to research a specific project. "
            "IMPORTANT: The project_id must be a real UUID from a previous search_projects result."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "The project UUID from a search_projects result. Must be a valid UUID.",
                },
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "batch_research_epc",
        "description": (
            "Research multiple projects at once to discover their EPC contractors. "
            "Use when a user asks to research several or all projects from a search. "
            "IMPORTANT: All project_ids must be real UUIDs from a previous search_projects result."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of project UUIDs from search_projects results. Must be valid UUIDs.",
                },
            },
            "required": ["project_ids"],
        },
    },
    {
        "name": "get_discoveries",
        "description": (
            "Look up existing EPC discovery results. "
            "Optionally filter by specific project IDs. "
            "Use when a user asks about confirmed EPCs or past research results."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of project IDs to filter by. Omit for all.",
                },
            },
        },
    },
    {
        "name": "query_knowledge_base",
        "description": (
            "Query the knowledge base for information about developers, EPC contractors, "
            "and their relationships. Returns entity profiles, known engagements, and "
            "research history. Use when a user asks 'what do we know about [company]?' "
            "or 'which EPCs are active in [state]?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_name": {
                    "type": "string",
                    "description": "Company name to look up (developer or EPC). Partial match not supported — use the full name.",
                },
                "state": {
                    "type": "string",
                    "description": "State abbreviation to find active EPCs (e.g. 'TX', 'CA').",
                },
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

def _is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


async def _execute_tool(tool_name: str, tool_input: dict) -> dict | list | str:
    """Execute a chat tool and return the result."""

    if tool_name == "search_projects":
        projects = db.search_projects(
            state=tool_input.get("state"),
            iso_region=tool_input.get("iso_region"),
            mw_min=tool_input.get("mw_min"),
            mw_max=tool_input.get("mw_max"),
            developer=tool_input.get("developer"),
            fuel_type=tool_input.get("fuel_type"),
            needs_research=tool_input.get("needs_research"),
            has_epc=tool_input.get("has_epc"),
            search=tool_input.get("search"),
            cod_min=tool_input.get("cod_min", "2025-01-01"),
            cod_max=tool_input.get("cod_max", "2028-12-31"),
            limit=tool_input.get("limit", 20),
        )
        return {"projects": projects, "count": len(projects)}

    elif tool_name == "research_epc":
        project_id = tool_input["project_id"]
        if not _is_valid_uuid(project_id):
            return {"error": f"Invalid project ID '{project_id}'. Use a real UUID from search_projects results."}
        project = db.get_project(project_id)
        if not project:
            return {"error": f"Project {project_id} not found"}

        existing = db.get_active_discovery(project_id)
        if existing and existing["review_status"] == "accepted":
            return {
                "skipped": True,
                "reason": "already_accepted",
                "discovery": existing,
            }

        knowledge_context = build_knowledge_context(project)
        result, agent_log, total_tokens = await run_agent_async(
            project, knowledge_context
        )
        discovery = db.store_discovery(
            project_id, result, agent_log, total_tokens, project=project
        )
        return {"discovery": discovery}

    elif tool_name == "batch_research_epc":
        project_ids = tool_input["project_ids"]
        invalid = [pid for pid in project_ids if not _is_valid_uuid(pid)]
        if invalid:
            return {"error": f"Invalid project IDs: {invalid}. Use real UUIDs from search_projects results."}
        projects = [db.get_project(pid) for pid in project_ids]
        projects = [p for p in projects if p is not None]

        if not projects:
            return {"error": "No valid projects found"}

        results = []

        async def on_progress(update: dict):
            results.append(update)

        await run_batch(projects, on_progress)
        return {
            "results": results,
            "total": len(projects),
            "completed": sum(
                1 for r in results if r.get("status") in ("completed", "skipped")
            ),
            "errors": sum(1 for r in results if r.get("status") == "error"),
        }

    elif tool_name == "get_discoveries":
        project_ids = tool_input.get("project_ids")
        if project_ids:
            discoveries = db.get_discoveries_for_projects(project_ids)
        else:
            discoveries = db.list_discoveries()
        return {"discoveries": discoveries, "count": len(discoveries)}

    elif tool_name == "query_knowledge_base":
        entity_name = tool_input.get("entity_name")
        state = tool_input.get("state")
        if not entity_name and not state:
            return {"error": "Provide at least one of entity_name or state."}
        result = query_knowledge_base(entity_name=entity_name, state=state)
        return {"knowledge": result}

    else:
        return {"error": f"Unknown tool: {tool_name}"}


# ---------------------------------------------------------------------------
# Streaming chat agent
# ---------------------------------------------------------------------------

async def run_chat_agent(
    messages: list[dict],
    conversation_id: str,
    stream_writer: StreamWriter,
) -> AsyncGenerator[str, None]:
    """Run the chat agent, yielding SSE events.

    Args:
        messages: Conversation history as [{role, content}, ...].
        conversation_id: For DB persistence.
        stream_writer: SSE protocol encoder.

    Yields:
        SSE-formatted strings for the frontend.
    """
    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Cache system prompt + tools to reduce input token costs (~90% savings)
    cached_system = [{
        "type": "text",
        "text": SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"},
    }]
    cached_tools = [*TOOLS[:-1], {**TOOLS[-1], "cache_control": {"type": "ephemeral"}}]

    message_id = str(uuid.uuid4())
    yield stream_writer.start(message_id)
    yield stream_writer.start_step()

    # Convert messages to Anthropic format
    api_messages = [{"role": m["role"], "content": m["content"]} for m in messages]

    full_text = ""
    all_parts: list[dict] = []

    for _round in range(MAX_TOOL_ROUNDS):
        # Stream the response
        tool_calls: list[dict] = []
        current_tool_input = ""
        current_text_part_id: str | None = None

        async with client.messages.stream(
            model=MODEL,
            max_tokens=4096,
            system=cached_system,
            tools=cached_tools,
            messages=api_messages,
        ) as stream:
            async for event in stream:

                # --- Text streaming ---
                if event.type == "content_block_start":
                    if event.content_block.type == "text":
                        current_text_part_id = str(len(all_parts))
                        yield stream_writer.text_start(current_text_part_id)

                    elif event.content_block.type == "tool_use":
                        tool_calls.append({
                            "id": event.content_block.id,
                            "name": event.content_block.name,
                            "input": {},
                        })
                        current_tool_input = ""
                        yield stream_writer.tool_input_start(
                            event.content_block.id,
                            event.content_block.name,
                        )

                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta" and current_text_part_id is not None:
                        full_text += event.delta.text
                        yield stream_writer.text_delta(
                            current_text_part_id, event.delta.text
                        )

                    elif event.delta.type == "input_json_delta":
                        current_tool_input += event.delta.partial_json

                elif event.type == "content_block_stop":
                    if current_text_part_id is not None:
                        yield stream_writer.text_end(current_text_part_id)
                        all_parts.append({"type": "text", "text": full_text})
                        current_text_part_id = None

                    elif tool_calls:
                        # Parse accumulated JSON input
                        tc = tool_calls[-1]
                        try:
                            tc["input"] = json.loads(current_tool_input) if current_tool_input else {}
                        except json.JSONDecodeError:
                            tc["input"] = {}

                        yield stream_writer.tool_input_available(
                            tc["id"], tc["name"], tc["input"]
                        )

            # Get the final message for stop_reason
            response = await stream.get_final_message()

        # Execute any tool calls
        if response.stop_reason == "tool_use" and tool_calls:
            tool_results = []
            for tc in tool_calls:
                output = await _execute_tool(tc["name"], tc["input"])
                yield stream_writer.tool_output_available(tc["id"], output)

                all_parts.append({
                    "type": "tool-invocation",
                    "toolCallId": tc["id"],
                    "toolName": tc["name"],
                    "input": tc["input"],
                    "output": output,
                })

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": json.dumps(output, default=str),
                })

            # Feed results back and loop
            api_messages.append({"role": "assistant", "content": response.content})
            api_messages.append({"role": "user", "content": tool_results})

            # Start a new step for the next round
            yield stream_writer.finish_step()
            yield stream_writer.start_step()

            # Reset for next round
            tool_calls = []
            full_text = ""
            continue

        # No more tool calls — we're done
        break

    yield stream_writer.finish_step()
    yield stream_writer.finish()
    yield stream_writer.done()

    # Persist the assistant message
    db.save_message(
        conversation_id=conversation_id,
        role="assistant",
        content=full_text,
        parts=all_parts,
    )
