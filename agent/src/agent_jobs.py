"""In-memory agent job store.

Tracks background chat agent runs so they survive client disconnects.
When a client reconnects, it can resume streaming from where it left off
using a cursor into the append-only event list.

Same pattern as batch_progress.py — completed jobs auto-cleaned after 5 min.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

# Active jobs: job_id -> AgentJob
_jobs: dict[str, AgentJob] = {}

# Conversation -> job_id for active (running) jobs only
_conv_jobs: dict[str, str] = {}

# How long to keep completed jobs before cleanup (seconds)
_CLEANUP_AFTER = 300  # 5 minutes


@dataclass
class AgentJob:
    job_id: str
    conversation_id: str
    status: str = "running"  # running | completed | error | cancelled
    events: list[str] = field(default_factory=list)
    done: bool = False
    error_message: str | None = None
    created_at: float = field(default_factory=time.time)
    _waiters: list[asyncio.Event] = field(default_factory=list)
    _task: asyncio.Task | None = None

    def append_event(self, event: str) -> None:
        """Add an SSE event string and notify all waiting subscribers."""
        self.events.append(event)
        self._notify()

    def _notify(self) -> None:
        for waiter in self._waiters:
            waiter.set()

    async def wait_for_update(self, timeout: float = 2.0) -> bool:
        """Block until a new event is appended. Returns True if notified."""
        event = asyncio.Event()
        self._waiters.append(event)
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            self._waiters.remove(event)


def create_job(job_id: str, conversation_id: str) -> AgentJob:
    """Register a new background agent job."""
    _cleanup_old()
    job = AgentJob(job_id=job_id, conversation_id=conversation_id)
    _jobs[job_id] = job
    _conv_jobs[conversation_id] = job_id
    return job


def get_job(job_id: str) -> AgentJob | None:
    return _jobs.get(job_id)


def get_active_job_for_conversation(conversation_id: str) -> AgentJob | None:
    """Find a running (not yet done) job for the given conversation."""
    job_id = _conv_jobs.get(conversation_id)
    if not job_id:
        return None
    job = _jobs.get(job_id)
    if job and not job.done:
        return job
    # Stale mapping — clean up
    _conv_jobs.pop(conversation_id, None)
    return None


def set_task(job_id: str, task: asyncio.Task) -> None:
    """Store the asyncio.Task reference so the job can be cancelled."""
    job = _jobs.get(job_id)
    if job:
        job._task = task


def mark_job_done(job_id: str, error: str | None = None) -> None:
    """Mark a job as finished (success or error)."""
    job = _jobs.get(job_id)
    if not job:
        return
    job.done = True
    job.status = "error" if error else "completed"
    job.error_message = error
    job._notify()
    # Remove from active conversation mapping
    _conv_jobs.pop(job.conversation_id, None)


def cancel_job(job_id: str) -> bool:
    """Cancel a running job. Returns True if cancelled, False if not found/already done.

    Only cancels the asyncio task — the CancelledError handler in
    _run_agent_job is responsible for appending finish events and
    calling mark_job_done, so stream readers see a clean close.
    """
    job = _jobs.get(job_id)
    if not job or job.done:
        return False
    if job._task and not job._task.done():
        job._task.cancel()
        return True
    # No task or task already finished — mark done directly
    job.done = True
    job.status = "cancelled"
    job._notify()
    _conv_jobs.pop(job.conversation_id, None)
    return True


def cancel_job_for_conversation(conversation_id: str) -> bool:
    """Cancel the active job for a conversation (if any). Used as fallback
    when the frontend doesn't have the job ID yet."""
    job = get_active_job_for_conversation(conversation_id)
    if not job:
        return False
    return cancel_job(job.job_id)


def _cleanup_old() -> None:
    """Remove jobs that completed more than _CLEANUP_AFTER seconds ago."""
    now = time.time()
    to_remove = [
        jid for jid, j in _jobs.items()
        if j.done and (now - j.created_at) > _CLEANUP_AFTER
    ]
    for jid in to_remove:
        del _jobs[jid]
