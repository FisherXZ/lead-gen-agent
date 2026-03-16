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

import anthropic
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import db
from .auth import get_user_id
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
from .batch_progress import cancel_batch, cancel_batch_for_conversation, get_batch
from .knowledge_base import build_knowledge_context, promote_discovery_to_kb, process_rejection_into_kb
from .research import run_research, run_research_plan
from .chat_agent import run_chat_agent
from .knowledge_base import get_entity_with_profile, list_entities, rebuild_profile_if_stale
from .models import AgentResult, BatchDiscoverRequest, ChatRequest, DiscoverPlanRequest, DiscoverRequest, EpcSource, NegativeEvidence, ReviewRequest
from .sse import StreamWriter

logger = logging.getLogger(__name__)


def _parse_reasoning(raw):
    """Parse JSON reasoning string back to dict for API response."""
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and "summary" in parsed:
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
    return raw

def require_auth(request: Request) -> str:
    """FastAPI dependency: extract JWT, verify, return user_id."""
    return get_user_id(request)


app = FastAPI(title="EPC Discovery Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-conversation-id", "x-vercel-ai-ui-message-stream", "x-job-id"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/settings/validate-key")
async def validate_key(request: Request, _user_id: str = Depends(require_auth)):
    """Validate a user-provided Anthropic API key."""
    key = request.headers.get("x-anthropic-api-key")
    if not key:
        raise HTTPException(400, "No key provided")
    try:
        client = anthropic.AsyncAnthropic(api_key=key)
        await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        return {"valid": True}
    except anthropic.AuthenticationError:
        return {"valid": False, "error": "Invalid API key"}
    except Exception as e:
        return {"valid": False, "error": type(e).__name__}


@app.post("/api/discover/plan")
async def discover_plan(req: DiscoverPlanRequest, request: Request, _user_id: str = Depends(require_auth)):
    """Generate a research plan for a project (without executing research).

    Returns the plan text for user review. The user can approve it and
    pass it to POST /api/discover with the plan parameter.
    """
    api_key = request.headers.get("x-anthropic-api-key")
    project = db.get_project(req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        knowledge_context = build_knowledge_context(project)
        plan_text, agent_log, total_tokens = await run_research_plan(
            project, knowledge_context, api_key=api_key
        )
    except KeyError as exc:
        raise HTTPException(status_code=503, detail=f"Missing configuration: {exc}")
    except Exception:
        tb = db.sanitize_key_from_string(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Planning error: {tb[:500]}")

    return {
        "project_id": req.project_id,
        "plan": plan_text,
        "tokens_used": total_tokens,
        "agent_log": agent_log,
    }


@app.post("/api/discover")
async def discover(req: DiscoverRequest, request: Request, _user_id: str = Depends(require_auth)):
    """Run EPC discovery for a project.

    Optionally accepts an approved plan from /api/discover/plan.
    """
    api_key = request.headers.get("x-anthropic-api-key")
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
            project, knowledge_context, approved_plan=req.plan, api_key=api_key
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Missing configuration: {exc}",
        )
    except Exception:
        tb = db.sanitize_key_from_string(traceback.format_exc())
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
        req.project_id, result, agent_log, total_tokens, project=project,
    )

    # Include error info in response if present (partial success)
    if result.error:
        discovery["error_category"] = result.error.category
        discovery["error_message"] = result.error.message

    # Signal that this discovery can be reviewed in chat
    discovery["handoff_available"] = True

    return discovery


@app.post("/api/discover/handoff")
async def discover_handoff(discovery_id: str = None, project_id: str = None, _user_id: str = Depends(require_auth)):
    """Create a new chat conversation pre-loaded with research context.

    Provide either discovery_id or project_id. Returns the conversation_id
    for the frontend to navigate to.
    """
    # Look up the discovery
    if discovery_id:
        client = db.get_client()
        resp = client.table("epc_discoveries").select("*").eq("id", discovery_id).execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail="Discovery not found")
        discovery = resp.data[0]
        project_id = discovery["project_id"]
    elif project_id:
        discovery_data = db.get_active_discovery(project_id)
        if not discovery_data:
            raise HTTPException(status_code=404, detail="No active discovery for project")
        discovery = discovery_data
    else:
        raise HTTPException(status_code=400, detail="Provide discovery_id or project_id")

    project = db.get_project(project_id)
    project_name = project.get("project_name", "Unknown") if project else "Unknown"

    # Build the research context summary
    epc = discovery.get("epc_contractor", "Unknown")
    confidence = discovery.get("confidence", "unknown")
    reasoning_raw = _parse_reasoning(discovery.get("reasoning", ""))
    if isinstance(reasoning_raw, dict):
        reasoning = reasoning_raw.get("summary", "")
    else:
        reasoning = reasoning_raw
    sources = discovery.get("sources", [])
    searches = discovery.get("searches_performed", [])

    source_lines = []
    for s in sources[:10]:
        line = f"- {s.get('publication') or s.get('channel', 'Source')}"
        if s.get("excerpt"):
            line += f": {s['excerpt'][:100]}"
        if s.get("url"):
            line += f" ({s['url']})"
        source_lines.append(line)

    context_msg = f"""Here is the research context for **{project_name}**:

**EPC Contractor:** {epc}
**Confidence:** {confidence}

**Reasoning:**
{reasoning}

**Sources ({len(sources)}):**
{chr(10).join(source_lines) if source_lines else "No sources found."}

**Searches Performed ({len(searches)}):**
{chr(10).join(f"- {s}" for s in searches[:15]) if searches else "None recorded."}

Discovery ID: `{discovery.get("id", "unknown")}`

You can ask me questions about this research, request more investigation, or approve/reject the finding."""

    # Create conversation and pre-populate
    conv = db.create_conversation(title=f"Review: {epc} for {project_name}")
    db.save_message(conv["id"], "assistant", context_msg)

    return {
        "conversation_id": conv["id"],
        "project_name": project_name,
        "epc_contractor": epc,
        "confidence": confidence,
    }


@app.post("/api/discover/batch")
async def discover_batch(req: BatchDiscoverRequest, request: Request, _user_id: str = Depends(require_auth)):
    """Run EPC discovery on multiple projects, streaming progress via SSE."""
    api_key = request.headers.get("x-anthropic-api-key")
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
            await run_batch(projects, on_progress, api_key=api_key)
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
def review_discovery(discovery_id: str, req: ReviewRequest, _user_id: str = Depends(require_auth)):
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
                neg_raw = discovery.get("negative_evidence") or []
                neg_evidence = [NegativeEvidence(**n) for n in neg_raw] if neg_raw else []
                result = AgentResult(
                    epc_contractor=discovery.get("epc_contractor"),
                    confidence=discovery.get("confidence", "unknown"),
                    sources=sources,
                    reasoning=_parse_reasoning(discovery.get("reasoning", "")),
                    related_leads=discovery.get("related_leads", []),
                    searches_performed=discovery.get("searches_performed", []),
                    negative_evidence=neg_evidence,
                )
                promote_discovery_to_kb(discovery["project_id"], result, project)
            except Exception:
                logger.error(
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
            logger.error(
                "KB rejection processing failed for discovery %s", discovery_id, exc_info=True
            )

    return updated


@app.get("/api/discoveries")
def list_discoveries(_user_id: str = Depends(require_auth)):
    """List all EPC discoveries."""
    discoveries = db.list_discoveries()
    for d in discoveries:
        d["reasoning"] = _parse_reasoning(d.get("reasoning", ""))
    return discoveries


@app.get("/api/discoveries/pending")
def list_pending_discoveries(_user_id: str = Depends(require_auth)):
    """List pending discoveries with project metadata, sorted by confidence."""
    discoveries = db.list_pending_discoveries()
    for d in discoveries:
        d["reasoning"] = _parse_reasoning(d.get("reasoning", ""))
    return discoveries


# ---------------------------------------------------------------------------
# Knowledge Base / Entity endpoints
# ---------------------------------------------------------------------------


@app.get("/api/entities")
def get_entities(type: str | None = None, limit: int = 50, _user_id: str = Depends(require_auth)):
    """List entities, optionally filtered by type ('developer' or 'epc')."""
    return list_entities(entity_type=type, limit=limit)


@app.get("/api/entities/{entity_id}")
def get_entity(entity_id: str, _user_id: str = Depends(require_auth)):
    """Get an entity by ID, including its profile."""
    entity = get_entity_with_profile(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


@app.post("/api/entities/{entity_id}/rebuild-profile")
def rebuild_entity_profile(entity_id: str, _user_id: str = Depends(require_auth)):
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


@app.post("/api/batch/{batch_id}/cancel")
def cancel_batch_endpoint(batch_id: str, _user_id: str = Depends(require_auth)):
    """Cancel a running batch research job."""
    cancelled = cancel_batch(batch_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Batch not found or already finished")
    return {"status": "cancelled"}


@app.post("/api/conversations/{conversation_id}/cancel-batch")
def cancel_conversation_batch(conversation_id: str, _user_id: str = Depends(require_auth)):
    """Cancel the active batch research for a conversation (keeps the chat job alive)."""
    cancelled = cancel_batch_for_conversation(conversation_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="No active batch for this conversation")
    return {"status": "cancelled"}


@app.get("/api/batch-progress/{batch_id}")
async def batch_progress(batch_id: str, _user_id: str = Depends(require_auth)):
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
        "cancelled": state.cancelled,
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
async def chat(req: ChatRequest, request: Request, _user_id: str = Depends(require_auth)):
    """Chat with the EPC discovery agent. Streams response via SSE.

    The agent runs as a background task so it survives client disconnects.
    If a job is already running for this conversation, reconnects to it.
    """
    api_key = request.headers.get("x-anthropic-api-key")
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
    task = asyncio.create_task(_run_agent_job(job, messages, conversation_id, stream_writer, api_key=api_key))
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
    job, messages: list[dict], conversation_id: str, stream_writer: StreamWriter,
    api_key: str | None = None,
) -> None:
    """Background wrapper: consumes the chat agent generator, pushes events to job store."""
    try:
        async for event in run_chat_agent(messages, conversation_id, stream_writer, api_key=api_key):
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
    except anthropic.AuthenticationError:
        error_sw = StreamWriter()
        job.append_event(error_sw.text("\n\n**Authentication failed.** Your API key is invalid or expired. Check Settings to update it."))
        job.append_event(error_sw.finish("error"))
        job.append_event(error_sw.done())
        mark_job_done(job.job_id, error="Authentication failed")
    except Exception:
        logger.exception("Agent job %s failed", job.job_id)
        # Push error events so any connected client sees the failure
        error_sw = StreamWriter()
        job.append_event(error_sw.finish("error"))
        job.append_event(error_sw.done())
        mark_job_done(job.job_id, error=db.sanitize_key_from_string(traceback.format_exc()[:500]))


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
async def chat_stream(job_id: str, cursor: int = Query(default=0), _user_id: str = Depends(require_auth)):
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
def cancel_agent_job(job_id: str, _user_id: str = Depends(require_auth)):
    """Cancel a running agent job."""
    cancelled = cancel_job(job_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Job not found or already finished")
    return {"status": "cancelled"}


@app.post("/api/conversations/{conversation_id}/cancel")
def cancel_conversation_job(conversation_id: str, _user_id: str = Depends(require_auth)):
    """Cancel the active agent job for a conversation.

    Fallback for when the frontend doesn't have the job ID yet
    (e.g. user hits stop during the 'submitted' phase).
    """
    cancelled = cancel_job_for_conversation(conversation_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="No active job for this conversation")
    return {"status": "cancelled"}


@app.get("/api/conversations/{conversation_id}/status")
def conversation_status(conversation_id: str, _user_id: str = Depends(require_auth)):
    """Check if an agent job is currently running for a conversation."""
    active = get_active_job_for_conversation(conversation_id)
    return {"active_job_id": active.job_id if active else None}


@app.get("/api/conversations")
def get_conversations(_user_id: str = Depends(require_auth)):
    """List recent chat conversations."""
    return db.list_conversations()


@app.get("/api/conversations/{conversation_id}/messages")
def get_conversation_messages(conversation_id: str, _user_id: str = Depends(require_auth)):
    """Get all messages for a conversation."""
    return db.get_conversation_messages(conversation_id)
