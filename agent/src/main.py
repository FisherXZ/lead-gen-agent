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
from .models import AgentResult, BatchDiscoverRequest, ChatRequest, ContactDiscoverRequest, DiscoverPlanRequest, DiscoverRequest, EpcSource, HubSpotConnectRequest, HubSpotPushRequest, NegativeEvidence, ReviewRequest
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
    conv = db.create_conversation(title=f"Review: {epc} for {project_name}", user_id=_user_id)
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
def review_discovery(discovery_id: str, req: ReviewRequest, request: Request, _user_id: str = Depends(require_auth)):
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

                # Auto-trigger contact discovery for the EPC entity
                epc_name = discovery.get("epc_contractor")
                if epc_name and epc_name != "Unknown":
                    try:
                        from .knowledge_base import resolve_entity
                        epc_entity = resolve_entity(epc_name)
                        if epc_entity:
                            api_key = request.headers.get("x-anthropic-api-key")
                            from .contact_discovery import discover_contacts
                            asyncio.create_task(
                                discover_contacts(epc_entity["id"], epc_name, api_key, project=project)
                            )
                            logger.info("Auto-triggered contact discovery for %s", epc_name)
                    except Exception:
                        logger.warning(
                            "Failed to auto-trigger contact discovery for %s", epc_name,
                            exc_info=True,
                        )
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
# Contact Discovery endpoints
# ---------------------------------------------------------------------------


@app.post("/api/contacts/discover")
async def discover_contacts_endpoint(
    req: ContactDiscoverRequest,
    request: Request,
    _user_id: str = Depends(require_auth),
):
    """Trigger contact discovery for an EPC entity."""
    entity_id = req.entity_id

    # Verify entity exists
    client = db.get_client()
    resp = client.table("entities").select("id, name").eq("id", entity_id).limit(1).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="Entity not found")

    entity = resp.data[0]
    api_key = request.headers.get("x-anthropic-api-key")

    from .contact_discovery import discover_contacts
    contacts = await discover_contacts(entity_id, entity["name"], api_key)

    return {"contacts": contacts, "entity_id": entity_id, "entity_name": entity["name"]}


@app.get("/api/contacts/{entity_id}")
def get_contacts(entity_id: str, _user_id: str = Depends(require_auth)):
    """Get cached contacts for an entity."""
    contacts = db.get_contacts_for_entity(entity_id)
    return {"contacts": contacts, "entity_id": entity_id}


# ---------------------------------------------------------------------------
# HubSpot Integration endpoints
# ---------------------------------------------------------------------------


@app.post("/api/hubspot/connect")
def hubspot_connect(req: HubSpotConnectRequest, _user_id: str = Depends(require_auth)):
    """Validate and save HubSpot Private App token."""
    from .hubspot import save_settings

    try:
        settings = save_settings(
            token=req.token,
            pipeline_id=req.pipeline_id,
            deal_stage_id=req.deal_stage_id,
        )
        return {"connected": True, "portal_id": settings.get("portal_id")}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("HubSpot connect failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save HubSpot settings")


@app.get("/api/hubspot/status")
def hubspot_status(_user_id: str = Depends(require_auth)):
    """Check HubSpot connection status."""
    from .hubspot import get_settings
    settings = get_settings()
    if settings and settings.get("enabled"):
        return {"connected": True, "portal_id": settings.get("portal_id")}
    return {"connected": False}


@app.post("/api/hubspot/push")
def hubspot_push(req: HubSpotPushRequest, _user_id: str = Depends(require_auth)):
    """Push a discovery to HubSpot (Company + Deal + Contacts)."""
    project_id = req.project_id

    from .hubspot import get_settings, push_discovery
    settings = get_settings()
    if not settings:
        raise HTTPException(status_code=400, detail="HubSpot is not connected. Configure in Settings.")

    token = settings.get("api_key")
    if not token:
        raise HTTPException(status_code=500, detail="Could not decrypt HubSpot token")

    # Look up project + entity + contacts
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    client = db.get_client()
    disc_resp = (
        client.table("epc_discoveries")
        .select("*")
        .eq("project_id", project_id)
        .eq("review_status", "accepted")
        .limit(1)
        .execute()
    )
    if not disc_resp.data:
        raise HTTPException(status_code=400, detail="No accepted discovery for this project")

    epc_name = disc_resp.data[0].get("epc_contractor")
    from .knowledge_base import resolve_entity
    entity = resolve_entity(epc_name) if epc_name else None
    if not entity:
        raise HTTPException(status_code=400, detail=f"EPC entity '{epc_name}' not found")

    contacts = db.get_contacts_for_entity(entity["id"])

    try:
        result = push_discovery(
            project=project,
            entity=entity,
            contacts=contacts,
            token=token,
            pipeline_id=settings.get("pipeline_id"),
            deal_stage_id=settings.get("deal_stage_id"),
        )
        return result
    except Exception as e:
        logger.error("HubSpot push failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"HubSpot push failed: {str(e)[:200]}")


@app.get("/api/hubspot/sync-log")
def hubspot_sync_log(_user_id: str = Depends(require_auth)):
    """Recent HubSpot sync history."""
    client = db.get_client()
    resp = (
        client.table("hubspot_sync_log")
        .select("*")
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return resp.data


# ---------------------------------------------------------------------------
# Sales Actions endpoint
# ---------------------------------------------------------------------------


@app.get("/api/actions")
def get_actions(_user_id: str = Depends(require_auth)):
    """Prioritized list of actionable discoveries with contacts.

    Returns accepted discoveries joined with project data, EPC entity,
    contacts, and HubSpot sync status. Sorted by lead_score descending.
    """
    client = db.get_client()

    # Get accepted discoveries with project info
    disc_resp = (
        client.table("epc_discoveries")
        .select(
            "id, epc_contractor, confidence, source_count, created_at, "
            "project:project_id(id, project_name, developer, mw_capacity, state, expected_cod, lead_score)"
        )
        .eq("review_status", "accepted")
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    )

    actions = []
    for disc in disc_resp.data:
        proj = disc.get("project") or {}
        epc_name = disc.get("epc_contractor", "")

        # Look up entity + contacts
        entity = resolve_entity(epc_name) if epc_name else None
        entity_id = entity["id"] if entity else None
        contacts = db.get_contacts_for_entity(entity_id) if entity_id else []

        # Check HubSpot sync status
        has_hubspot_sync = False
        if entity_id:
            sync_resp = (
                client.table("hubspot_sync_log")
                .select("id")
                .eq("entity_id", entity_id)
                .eq("sync_status", "success")
                .eq("hubspot_object_type", "company")
                .limit(1)
                .execute()
            )
            has_hubspot_sync = bool(sync_resp.data)

        # Contact discovery status
        contact_status = entity.get("contact_discovery_status") if entity else None

        actions.append({
            "discovery_id": disc["id"],
            "project_id": proj.get("id"),
            "project_name": proj.get("project_name"),
            "developer": proj.get("developer"),
            "mw_capacity": proj.get("mw_capacity"),
            "state": proj.get("state"),
            "expected_cod": proj.get("expected_cod"),
            "lead_score": proj.get("lead_score"),
            "epc_contractor": epc_name,
            "confidence": disc.get("confidence"),
            "entity_id": entity_id,
            "contacts": contacts,
            "contact_count": len(contacts),
            "contact_discovery_status": contact_status,
            "has_hubspot_sync": has_hubspot_sync,
        })

    # Sort by lead_score descending
    actions.sort(key=lambda a: a.get("lead_score") or 0, reverse=True)
    return actions


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
# Reverse sweep endpoint
# ---------------------------------------------------------------------------

# Guard: prevent duplicate sweeps
_sweep_running = False


@app.post("/api/reverse-sweep")
async def reverse_sweep(request: Request, _user_id: str = Depends(require_auth)):
    """Run a reverse-lookup EPC sweep across all seeded EPCs.

    Searches SEC EDGAR, OSHA, and EPC portfolio pages for each known EPC,
    then matches results against the project queue. Creates pending discoveries
    for matches. Streams progress via SSE.
    """
    global _sweep_running
    if _sweep_running:
        raise HTTPException(status_code=409, detail="A reverse sweep is already running")

    api_key = request.headers.get("x-anthropic-api-key")

    async def event_stream():
        global _sweep_running
        _sweep_running = True

        queue: asyncio.Queue[dict | None] = asyncio.Queue()

        async def on_progress(update):
            await queue.put({
                "epc_name": update.epc_name,
                "status": update.status,
                "candidates_found": update.candidates_found,
                "matches_found": update.matches_found,
                "message": update.message,
            })

        async def run():
            from .reverse_sweep import run_reverse_sweep
            try:
                result = await run_reverse_sweep(on_progress=on_progress, api_key=api_key)
                await queue.put({
                    "status": "done",
                    "epcs_processed": result.epcs_processed,
                    "total_candidates": result.total_candidates,
                    "total_matches": result.total_matches,
                    "discoveries_created": result.discoveries_created,
                    "errors": result.errors[:10],
                })
            except Exception as exc:
                logger.exception("Reverse sweep failed")
                await queue.put({
                    "status": "error",
                    "message": str(exc)[:500],
                })
            finally:
                await queue.put(None)

        task = asyncio.create_task(run())

        try:
            while True:
                update = await queue.get()
                if update is None:
                    break
                yield f"data: {json.dumps(update)}\n\n"
        finally:
            _sweep_running = False
            if not task.done():
                task.cancel()

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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
        conv = db.create_conversation(title=first_text[:80], user_id=_user_id)
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
    """List recent chat conversations for the current user."""
    return db.list_conversations(user_id=_user_id)


@app.get("/api/conversations/{conversation_id}/messages")
def get_conversation_messages(conversation_id: str, _user_id: str = Depends(require_auth)):
    """Get all messages for a conversation (only if owned by current user)."""
    return db.get_conversation_messages(conversation_id, user_id=_user_id)
