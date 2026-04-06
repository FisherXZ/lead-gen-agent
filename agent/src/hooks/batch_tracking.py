"""BatchTrackingHook — batch progress setup for batch_research_epc."""
from __future__ import annotations
import uuid
from ..runtime import Hook, HookAction, RunContext

class BatchTrackingHook(Hook):
    async def pre_tool(self, tool_name: str, tool_input: dict, context: RunContext) -> HookAction:
        if tool_name != "batch_research_epc":
            return HookAction.continue_with(tool_input)
        from .. import db
        from ..batch_progress import create_batch, get_cancel_event, update_project, mark_done
        batch_id = str(uuid.uuid4())
        batch_projects = []
        for pid in tool_input.get("project_ids", []):
            p = db.get_project(pid)
            if p:
                batch_projects.append(p)
        create_batch(batch_id, batch_projects, conversation_id=context.conversation_id)

        async def on_progress(update: dict, _bid: str = batch_id):
            update_project(_bid, update)

        modified = dict(tool_input)
        modified["_batch_id"] = batch_id
        modified["_project_names"] = {p["id"]: p.get("project_name") or p.get("queue_id", p["id"]) for p in batch_projects}
        modified["_progress_callback"] = on_progress
        modified["_cancel_event"] = get_cancel_event(batch_id)
        return HookAction.continue_with(modified)

    async def post_tool(self, tool_name: str, tool_input: dict, result: dict, context: RunContext) -> dict:
        batch_id = tool_input.get("_batch_id")
        if tool_name == "batch_research_epc" and batch_id:
            from ..batch_progress import mark_done
            mark_done(batch_id)
        return result
