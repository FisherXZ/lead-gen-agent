"""run_research — research as a sub-agent tool (manager pattern).

When the chat agent calls this tool, it spawns a focused research
sub-runtime that runs autonomously and returns findings.
"""

from __future__ import annotations

import asyncio

DEFINITION = {
    "name": "run_research",
    "description": (
        "Launch a focused EPC research session for a project. "
        "Runs autonomously and returns findings including EPC contractor, "
        "confidence level, and sources."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "project_id": {"type": "integer", "description": "The project ID to research"},
            "focus": {"type": "string", "description": "Optional focus area"},
        },
        "required": ["project_id"],
    },
}


async def execute(tool_input: dict) -> dict:
    # Lazy imports to avoid circular: tools -> agents -> tools
    from .. import db
    from ..agents.research import build_research_runtime
    from ..knowledge_base import build_knowledge_context
    from ..prompts import build_user_message

    project_id = tool_input["project_id"]
    focus = tool_input.get("focus", "")
    api_key = tool_input.get("_api_key")

    project = db.get_project(project_id)
    if not project:
        return {"error": f"Project {project_id} not found"}

    kb_context = build_knowledge_context(project)
    runtime = build_research_runtime(project=project, api_key=api_key)

    user_msg = build_user_message(project, kb_context)
    if focus:
        user_msg += f"\n\nFocus: {focus}"

    try:
        result = await runtime.run_turn(
            messages=[{"role": "user", "content": user_msg}],
            on_event=lambda e: None,
        )

        # Extract findings from last assistant message
        summary = ""
        for msg in reversed(result.messages):
            if msg.get("role") == "assistant":
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            summary = block.get("text", "")
                            break
                elif isinstance(content, str):
                    summary = content
                break

        return {
            "findings": summary,
            "iterations": result.iterations,
            "project_name": project.get("project_name", ""),
        }
    except asyncio.CancelledError:
        raise  # Don't swallow task cancellation
    except Exception as exc:
        return {"error": f"Research failed: {type(exc).__name__}: {exc}"}
