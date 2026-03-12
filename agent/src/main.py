"""FastAPI app for EPC discovery agent."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import traceback
import uuid

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import db
from .agent_jobs import (
    cancel_job,
    cancel_job_for_conversation,
    create_job,
    get_active_job_for_conversation,
    get_job,
    mark_job_done,
    set_task,
)
from .batch import run_batch
from .batch_progress import get_batch
from .knowledge_base import build_knowledge_context, promote_discovery_to_kb, process_rejection_into_kb
from .research import run_research
from .chat_agent import run_chat_agent
from .knowledge_base import get_entity_with_profile, list_entities, rebuild_profile_if_stale
from .models import AgentResult, BatchDiscoverRequest, ChatRequest, DiscoverRequest, EpcSource, ReviewRequest
from .sse import StreamWriter

logger = logging.getLogger(__name__)

app = FastAPI(title="EPC Discovery Agent")

_default_origins = ["http://localhost:3000", "http://localhost:3001"]
_extra = os.environ.get("CORS_ORIGINS", "")  # comma-separated extra origins
_origins = _default_origins + [o.strip() for o in _extra.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-conversation-id", "x-vercel-ai-ui-message-stream", "x-job-id"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/discover")
async def discover(req: DiscoverRequest):
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

    # Run the research agent
    try:
        knowledge_context = build_knowledge_context(project)
        result, agent_log, total_tokens = await run_research(
            project, knowledge_context
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Missing configuration: {exc}",
        )
    except Exception:
        tb = traceback.format_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Agent error: {tb[:500]}",
        )

    # Check for fatal API errors — don't store garbage data
    if result.error:
        if result.error.category == "api_key_missing":
            raise HTTPException(
                status_code=401,
                detail=result.error.message,
            )
        elif result.error.category == "anthropic_error":
            raise HTTPException(
                status_code=429,
                detail=result.error.message,
            )

    # Store discovery for successful results or partial failures worth saving
    # (max_iterations, no_report, search_tool_error still have useful partial data)
    discovery = db.store_discovery(
        req.project_id, result, agent_log, total_tokens, project=project
    )

    # Include error info in response if present (partial success)
    if result.error:
        discovery["error_category"] = result.error.category
        discovery["error_message"] = result.error.message

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

    if req.action == "accepted":
        updated = db.update_discovery(discovery_id, {"review_status": req.action})
        db.update_project_epc(discovery["project_id"], discovery["epc_contractor"])

        # Promote to knowledge base — reconstruct AgentResult from stored data
        project = db.get_project(discovery["project_id"])
        if project:
            try:
                sources = [EpcSource(**s) for s in (discovery.get("sources") or [])]
                result = AgentResult(
                    epc_contractor=discovery.get("epc_contractor"),
                    confidence=discovery.get("confidence", "unknown"),
                    sources=sources,
                    reasoning=discovery.get("reasoning", ""),
                    related_leads=discovery.get("related_leads", []),
                    searches_performed=discovery.get("searches_performed", []),
                )
                promote_discovery_to_kb(discovery["project_id"], result, project)
            except Exception:
                import logging
                logging.getLogger(__name__).warning(
                    "KB promotion failed for discovery %s", discovery_id, exc_info=True
                )
    else:
        # Rejected
        update_data = {"review_status": req.action}
        if req.reason:
            update_data["rejection_reason"] = req.reason
        updated = db.update_discovery(discovery_id, update_data)

        try:
            process_rejection_into_kb(discovery, req.reason)
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "KB rejection processing failed for discovery %s", discovery_id, exc_info=True
            )

    return updated


@app.get("/api/discoveries")
def list_discoveries():
    """List all EPC discoveries."""
    return db.list_discoveries()


@app.get("/api/discoveries/pending")
def list_pending_discoveries():
    """List pending discoveries with project metadata, sorted by confidence."""
    return db.list_pending_discoveries()


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
# Batch progress SSE endpoint
# ---------------------------------------------------------------------------


@app.get("/api/batch-progress/{batch_id}")
async def batch_progress(batch_id: str):
    """Stream batch research progress as SSE events."""
    state = get_batch(batch_id)
    if not state:
        raise HTTPException(status_code=404, detail="Batch not found")

    async def event_stream():
        # Send initial snapshot
        yield f"data: {json.dumps(_batch_snapshot(state))}\n\n"

        # Stream updates until done
        while not state.done:
            notified = await state.wait_for_update(timeout=2.0)
            if notified or state.done:
                yield f"data: {json.dumps(_batch_snapshot(state))}\n\n"

        # Final snapshot
        yield f"data: {json.dumps(_batch_snapshot(state))}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _batch_snapshot(state) -> dict:
    """Build a JSON-serializable snapshot of batch state."""
    return {
        "batch_id": state.batch_id,
        "total": state.total,
        "completed": state.completed,
        "errors": state.errors,
        "done": state.done,
        "projects": [
            {
                "project_id": p.project_id,
                "project_name": p.project_name,
                "status": p.status,
                **({"epc_contractor": p.epc_contractor} if p.epc_contractor else {}),
                **({"confidence": p.confidence} if p.confidence else {}),
            }
            for p in state.projects
        ],
    }


# ---------------------------------------------------------------------------
# Chat endpoints
# ---------------------------------------------------------------------------


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Chat with the EPC discovery agent. Streams response via SSE.

    The agent runs as a background task so it survives client disconnects.
    If a job is already running for this conversation, reconnects to it.
    """
    # Create or reuse conversation
    if req.conversation_id:
        conversation_id = req.conversation_id
    else:
        first_text = req.messages[0].get_text() if req.messages else "New conversation"
        conv = db.create_conversation(title=first_text[:80])
        conversation_id = conv["id"]

    # If agent is already running for this conversation, reconnect
    existing_job = get_active_job_for_conversation(conversation_id)
    if existing_job:
        return StreamingResponse(
            _stream_from_job(existing_job, cursor=0),
            media_type="text/event-stream",
            headers={
                "x-vercel-ai-ui-message-stream": "v1",
                "x-conversation-id": conversation_id,
                "x-job-id": existing_job.job_id,
            },
        )

    # Save the latest user message (text + file metadata, no base64 data)
    user_msgs = [m for m in req.messages if m.role == "user"]
    if user_msgs:
        last = user_msgs[-1]
        # Build parts for persistence (strip base64 data to keep DB small)
        persist_parts = None
        if last.parts:
            persist_parts = []
            for p in last.parts:
                if p.type == "text":
                    persist_parts.append({"type": "text", "text": p.text})
                elif p.type == "file":
                    persist_parts.append({
                        "type": "file",
                        "mediaType": p.mediaType,
                        "filename": p.filename,
                        # Omit url (base64 data) to keep DB small
                    })
        db.save_message(conversation_id, "user", last.get_text(), parts=persist_parts)

    # Build message history for the agent (Anthropic API needs role + content)
    # Use get_content_blocks() to pass file attachments as native Claude content blocks
    messages = [{"role": m.role, "content": m.get_content_blocks()} for m in req.messages]

    # Create job and spawn background task
    job_id = str(uuid.uuid4())
    job = create_job(job_id, conversation_id)

    stream_writer = StreamWriter()
    task = asyncio.create_task(_run_agent_job(job, messages, conversation_id, stream_writer))
    set_task(job_id, task)

    return StreamingResponse(
        _stream_from_job(job, cursor=0),
        media_type="text/event-stream",
        headers={
            "x-vercel-ai-ui-message-stream": "v1",
            "x-conversation-id": conversation_id,
            "x-job-id": job_id,
        },
    )


async def _run_agent_job(
    job, messages: list[dict], conversation_id: str, stream_writer: StreamWriter
) -> None:
    """Background wrapper: consumes the chat agent generator, pushes events to job store."""
    try:
        async for event in run_chat_agent(messages, conversation_id, stream_writer):
            job.append_event(event)
        mark_job_done(job.job_id)
    except asyncio.CancelledError:
        logger.info("Agent job %s cancelled by user", job.job_id)
        # Push clean stop events so the frontend closes gracefully
        sw = StreamWriter()
        job.append_event(sw.finish_step())
        job.append_event(sw.finish("stop"))
        job.append_event(sw.done())
        # Now mark done — this notifies stream readers AFTER finish events are appended
        mark_job_done(job.job_id)
        db.save_message(
            conversation_id=conversation_id,
            role="assistant",
            content="[Stopped by user]",
        )
    except Exception:
        logger.exception("Agent job %s failed", job.job_id)
        # Push error events so any connected client sees the failure
        error_sw = StreamWriter()
        job.append_event(error_sw.finish("error"))
        job.append_event(error_sw.done())
        mark_job_done(job.job_id, error=traceback.format_exc()[:500])


async def _stream_from_job(job, cursor: int = 0):
    """Yield SSE events from a job, starting at cursor. Safe to disconnect."""
    while True:
        # Replay any events we haven't sent yet
        while cursor < len(job.events):
            yield job.events[cursor]
            cursor += 1

        # If job is done, we've sent everything
        if job.done:
            break

        # Wait for more events
        await job.wait_for_update(timeout=2.0)


@app.get("/api/chat-stream/{job_id}")
async def chat_stream(job_id: str, cursor: int = Query(default=0)):
    """Reconnect to a running or completed agent job's SSE stream."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return StreamingResponse(
        _stream_from_job(job, cursor=cursor),
        media_type="text/event-stream",
        headers={
            "x-vercel-ai-ui-message-stream": "v1",
            "x-conversation-id": job.conversation_id,
            "x-job-id": job_id,
        },
    )


@app.post("/api/jobs/{job_id}/cancel")
def cancel_agent_job(job_id: str):
    """Cancel a running agent job."""
    cancelled = cancel_job(job_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Job not found or already finished")
    return {"status": "cancelled"}


@app.post("/api/conversations/{conversation_id}/cancel")
def cancel_conversation_job(conversation_id: str):
    """Cancel the active agent job for a conversation.

    Fallback for when the frontend doesn't have the job ID yet
    (e.g. user hits stop during the 'submitted' phase).
    """
    cancelled = cancel_job_for_conversation(conversation_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="No active job for this conversation")
    return {"status": "cancelled"}


@app.get("/api/conversations/{conversation_id}/status")
def conversation_status(conversation_id: str):
    """Check if an agent job is currently running for a conversation."""
    active = get_active_job_for_conversation(conversation_id)
    return {"active_job_id": active.job_id if active else None}


@app.get("/api/conversations")
def get_conversations():
    """List recent chat conversations."""
    return db.list_conversations()


@app.get("/api/conversations/{conversation_id}/messages")
def get_conversation_messages(conversation_id: str):
    """Get all messages for a conversation."""
    return db.get_conversation_messages(conversation_id)
