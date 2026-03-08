"""FastAPI app for EPC discovery agent."""

from __future__ import annotations

import asyncio
import json
import traceback

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import db
from .agent import run_agent
from .batch import run_batch
from .chat_agent import run_chat_agent
from .knowledge_base import (
    get_entity_with_profile,
    list_entities,
    rebuild_profile_if_stale,
)
from .models import BatchDiscoverRequest, ChatRequest, DiscoverRequest, ReviewRequest
from .sse import StreamWriter

app = FastAPI(title="EPC Discovery Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-conversation-id", "x-vercel-ai-ui-message-stream"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/discover")
def discover(req: DiscoverRequest):
    """Run EPC discovery for a project."""
    project = db.get_project(req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check for existing active discovery
    existing = db.get_active_discovery(req.project_id)
    if existing and existing["review_status"] == "accepted":
        raise HTTPException(
            status_code=409,
            detail="Project already has an accepted EPC discovery",
        )

    # Run the agent
    try:
        result, agent_log, total_tokens = run_agent(project)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail=f"Agent error: {traceback.format_exc()}",
        )

    discovery = db.store_discovery(req.project_id, result, agent_log, total_tokens)
    return discovery


@app.post("/api/discover/batch")
async def discover_batch(req: BatchDiscoverRequest):
    """Run EPC discovery on multiple projects, streaming progress via SSE."""
    if not req.project_ids:
        raise HTTPException(status_code=400, detail="project_ids must not be empty")

    # Look up all projects
    projects: list[dict] = []
    for pid in req.project_ids:
        project = db.get_project(pid)
        if project:
            projects.append(project)

    if not projects:
        raise HTTPException(status_code=404, detail="No valid projects found")

    async def event_stream():
        queue: asyncio.Queue[dict | None] = asyncio.Queue()

        async def on_progress(update: dict):
            await queue.put(update)

        async def run():
            await run_batch(projects, on_progress)
            await queue.put(None)  # sentinel

        task = asyncio.create_task(run())

        completed = 0
        total = len(projects)

        while True:
            update = await queue.get()
            if update is None:
                # Send final done event
                yield f"data: {json.dumps({'type': 'done', 'completed': completed, 'total': total})}\n\n"
                break

            status = update.get("status")
            if status == "started":
                payload = {
                    "type": "started",
                    "project_id": update["project_id"],
                    "project_name": update.get("project_name", ""),
                    "completed": completed,
                    "total": total,
                }
            elif status == "completed":
                completed += 1
                payload = {
                    "type": "completed",
                    "project_id": update["project_id"],
                    "discovery": update["discovery"],
                    "completed": completed,
                    "total": total,
                }
            elif status == "skipped":
                completed += 1
                payload = {
                    "type": "skipped",
                    "project_id": update["project_id"],
                    "reason": update.get("reason", ""),
                    "completed": completed,
                    "total": total,
                }
            elif status == "error":
                completed += 1
                payload = {
                    "type": "error",
                    "project_id": update["project_id"],
                    "error": update.get("error", "Unknown error"),
                    "completed": completed,
                    "total": total,
                }
            else:
                continue

            yield f"data: {json.dumps(payload)}\n\n"

        await task

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.patch("/api/discover/{discovery_id}/review")
def review_discovery(discovery_id: str, req: ReviewRequest):
    """Accept or reject an EPC discovery."""
    if req.action not in ("accepted", "rejected"):
        raise HTTPException(status_code=400, detail="Action must be 'accepted' or 'rejected'")

    client = db.get_client()
    resp = client.table("epc_discoveries").select("*").eq("id", discovery_id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Discovery not found")

    discovery = resp.data[0]
    updated = db.update_discovery(discovery_id, {"review_status": req.action})

    # If accepted, also update the project's epc_company field
    if req.action == "accepted":
        db.update_project_epc(discovery["project_id"], discovery["epc_contractor"])

    return updated


@app.get("/api/discoveries")
def list_discoveries():
    """List all EPC discoveries."""
    return db.list_discoveries()


# ---------------------------------------------------------------------------
# Knowledge Base / Entity endpoints
# ---------------------------------------------------------------------------


@app.get("/api/entities")
def get_entities(type: str | None = None, limit: int = 50):
    """List entities, optionally filtered by type ('developer' or 'epc')."""
    return list_entities(entity_type=type, limit=limit)


@app.get("/api/entities/{entity_id}")
def get_entity(entity_id: str):
    """Get an entity by ID, including its profile."""
    entity = get_entity_with_profile(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


@app.post("/api/entities/{entity_id}/rebuild-profile")
def rebuild_entity_profile(entity_id: str):
    """Force-rebuild an entity's profile from current KB data."""
    # Verify entity exists
    client = db.get_client()
    resp = client.table("entities").select("id").eq("id", entity_id).limit(1).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Clear profile_rebuilt_at to force rebuild, then rebuild
    client.table("entities").update(
        {"profile_rebuilt_at": None}
    ).eq("id", entity_id).execute()

    profile = rebuild_profile_if_stale(entity_id)
    return {"entity_id": entity_id, "profile": profile}


# ---------------------------------------------------------------------------
# Chat endpoints
# ---------------------------------------------------------------------------


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Chat with the EPC discovery agent. Streams response via SSE."""
    # Create or reuse conversation
    if req.conversation_id:
        conversation_id = req.conversation_id
    else:
        first_text = req.messages[0].get_text() if req.messages else "New conversation"
        conv = db.create_conversation(title=first_text[:80])
        conversation_id = conv["id"]

    # Save the latest user message
    user_msgs = [m for m in req.messages if m.role == "user"]
    if user_msgs:
        db.save_message(conversation_id, "user", user_msgs[-1].get_text())

    # Build message history for the agent (Anthropic API needs role + content)
    messages = [{"role": m.role, "content": m.get_text()} for m in req.messages]

    stream_writer = StreamWriter()

    return StreamingResponse(
        run_chat_agent(messages, conversation_id, stream_writer),
        media_type="text/event-stream",
        headers={
            "x-vercel-ai-ui-message-stream": "v1",
            "x-conversation-id": conversation_id,
        },
    )


@app.get("/api/conversations")
def get_conversations():
    """List recent chat conversations."""
    return db.list_conversations()


@app.get("/api/conversations/{conversation_id}/messages")
def get_conversation_messages(conversation_id: str):
    """Get all messages for a conversation."""
    return db.get_conversation_messages(conversation_id)
