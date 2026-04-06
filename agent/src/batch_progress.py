"""In-memory batch progress store.

Tracks per-project status for active batch runs so the frontend
can poll /api/batch-progress/{batch_id} for live updates.

Entries are cleaned up when the batch completes.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

# Active batches: batch_id -> BatchState
_batches: dict[str, BatchState] = {}

# Conversation -> active batch_id mapping (for cancel-by-conversation)
_conversation_batches: dict[str, str] = {}

# How long to keep completed batches before cleanup (seconds)
_CLEANUP_AFTER = 300  # 5 minutes


@dataclass
class ProjectState:
    project_id: str
    project_name: str
    status: str = "waiting"  # waiting | researching | completed | skipped | error
    epc_contractor: str | None = None
    confidence: str | None = None


@dataclass
class BatchState:
    batch_id: str
    projects: list[ProjectState] = field(default_factory=list)
    done: bool = False
    cancelled: bool = False
    created_at: float = field(default_factory=time.time)
    # Subscribers waiting for updates
    _waiters: list[asyncio.Event] = field(default_factory=list)
    # Cancellation signal — checked by _research_one before starting work
    _cancel_event: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def total(self) -> int:
        return len(self.projects)

    @property
    def completed(self) -> int:
        return sum(
            1 for p in self.projects if p.status in ("completed", "skipped", "error", "cancelled")
        )

    @property
    def errors(self) -> int:
        return sum(1 for p in self.projects if p.status == "error")

    def notify_subscribers(self):
        for event in self._waiters:
            event.set()

    async def wait_for_update(self, timeout: float = 2.0) -> bool:
        """Wait for a status change. Returns True if notified, False on timeout."""
        event = asyncio.Event()
        self._waiters.append(event)
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return True
        except TimeoutError:
            return False
        finally:
            self._waiters.remove(event)


def create_batch(
    batch_id: str, projects: list[dict], conversation_id: str | None = None
) -> BatchState:
    """Register a new batch with its project list."""
    _cleanup_old()
    state = BatchState(
        batch_id=batch_id,
        projects=[
            ProjectState(
                project_id=p["id"],
                project_name=p.get("project_name") or p.get("queue_id", p["id"]),
            )
            for p in projects
        ],
    )
    _batches[batch_id] = state
    if conversation_id:
        _conversation_batches[conversation_id] = batch_id
    return state


def get_batch(batch_id: str) -> BatchState | None:
    return _batches.get(batch_id)


def update_project(batch_id: str, update: dict) -> None:
    """Update a project's status within a batch."""
    state = _batches.get(batch_id)
    if not state:
        return

    project_id = update.get("project_id")
    status = update.get("status", "")

    for p in state.projects:
        if p.project_id == project_id:
            if status == "started":
                p.status = "researching"
            elif status == "completed":
                p.status = "completed"
                disc = update.get("discovery", {})
                p.epc_contractor = disc.get("epc_contractor")
                p.confidence = disc.get("confidence")
            elif status == "skipped":
                p.status = "skipped"
            elif status == "error":
                p.status = "error"
            break

    state.notify_subscribers()


def mark_done(batch_id: str) -> None:
    """Mark a batch as complete."""
    state = _batches.get(batch_id)
    if state:
        state.done = True
        state.notify_subscribers()


def get_cancel_event(batch_id: str) -> asyncio.Event | None:
    """Get the cancellation event for a batch (passed into run_batch)."""
    state = _batches.get(batch_id)
    return state._cancel_event if state else None


def cancel_batch(batch_id: str) -> bool:
    """Cancel a running batch. Returns True if cancelled, False if not found/already done."""
    state = _batches.get(batch_id)
    if not state or state.done:
        return False

    state.cancelled = True
    # Signal all _research_one coroutines to stop before starting new work
    state._cancel_event.set()

    # Mark remaining "waiting" projects as "cancelled"
    for p in state.projects:
        if p.status == "waiting":
            p.status = "cancelled"

    state.done = True
    state.notify_subscribers()
    return True


def cancel_batch_for_conversation(conversation_id: str) -> bool:
    """Cancel the active batch for a conversation. Returns True if cancelled."""
    batch_id = _conversation_batches.get(conversation_id)
    if not batch_id:
        return False
    return cancel_batch(batch_id)


def _cleanup_old() -> None:
    """Remove batches that completed more than _CLEANUP_AFTER seconds ago."""
    now = time.time()
    to_remove = [
        bid for bid, s in _batches.items() if s.done and (now - s.created_at) > _CLEANUP_AFTER
    ]
    for bid in to_remove:
        del _batches[bid]
