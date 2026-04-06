# Streaming Resilience Design

**Date:** 2026-04-06  
**Status:** Approved  
**Type:** Proactive hardening

## Problem

The chat agent streams SSE events over a long-lived HTTP connection. Three gaps exist:

1. **No reconnection protocol** — SSE events have no `id:` fields, so browsers can't send `Last-Event-ID` on reconnect. The cursor-based replay infrastructure in `agent_jobs.py` exists but is never used by the client after a network drop.
2. **No heartbeats** — idle connections (waiting between tool calls) are silently dropped by proxies and load balancers with no signal to the client.
3. **Unbounded memory** — `AgentJob.events` grows without limit for the 5-minute job lifetime. No cap exists.

**Not a problem:** Backpressure. The Anthropic API rate-limits token output to ~50 tokens/s (~10 events/s). TCP flow control is sufficient. No additional backpressure mechanism is warranted.

## What Already Exists (Don't Re-Build)

- `agent_jobs.py` — append-only event log per job, cursor-based replay via `_stream_from_job(job, cursor=N)`
- `/api/chat-stream/{job_id}?cursor=N` — reconnection endpoint, fully functional
- `x-job-id` response header — clients already receive the job ID
- `POST /api/chat` auto-reconnect — if a job is already running for a conversation, it reconnects (cursor=0)

The design is close to the industry standard (Vercel Workflow DevKit, LangGraph). The delta is surgical.

## Design

### Layer 1 — SSE Protocol Compliance

**`agent/src/sse.py`**

`_event()` moves from a module-level function to an instance method on `StreamWriter` (it currently delegates through instance methods anyway). `StreamWriter` gains a `_seq: int = 0` counter incremented on every emission.

```python
def _event(self, payload: dict) -> str:
    seq = self._seq
    self._seq += 1
    return f"id: {seq}\ndata: {json.dumps(payload)}\n\n"
```

Every SSE event gains an `id:` line. The value equals the 0-based index in `job.events`, which is also the cursor value for `/api/chat-stream/{job_id}?cursor=N`.

**`agent/src/main.py` — `/api/chat` endpoint**

Before creating a new job, read `Last-Event-ID`:

```python
last_event_id = request.headers.get("last-event-id")
if last_event_id is not None:
    # Try to find an existing job for this conversation
    existing_job = get_active_job_for_conversation(conversation_id)
    if existing_job:
        cursor = int(last_event_id) + 1
        return StreamingResponse(
            _stream_from_job(existing_job, cursor=cursor),
            media_type="text/event-stream",
            headers={...}
        )
```

Browsers using native `EventSource` get free reconnection with zero additional client code. The fetch-based `useChat` path benefits via Layer 3.

### Layer 2 — Resilience Guards

**`agent/src/agent_jobs.py`**

**Heartbeats:** Emit an SSE comment every 15 seconds during idle waits. SSE comments (lines starting with `:`) are ignored by all parsers — no client code changes needed — but they keep the TCP connection alive through proxies.

```python
async def _stream_from_job(job, cursor: int = 0):
    last_ping = time.monotonic()
    while True:
        while cursor < len(job.events):
            yield job.events[cursor]
            cursor += 1
        if job.done:
            break
        now = time.monotonic()
        if now - last_ping > 15:
            yield ": ping\n\n"
            last_ping = now
        await job.wait_for_update(timeout=2.0)
```

**Memory cap:** Add `_total_bytes: int` and enforce a 4MB cap in `append_event`. Events past the cap are dropped from the replay log (a warning is logged) but the live stream is unaffected. At ~100 bytes/event, 4MB ≈ 40,000 events — roughly 10 full batch research runs.

```python
MAX_EVENT_BYTES = 4 * 1024 * 1024

def append_event(self, event: str) -> None:
    if self._total_bytes + len(event) <= MAX_EVENT_BYTES:
        self.events.append(event)
        self._total_bytes += len(event)
    else:
        logger.warning("Job %s event log full (%d bytes), dropping from replay", 
                       self.job_id, self._total_bytes)
    self._notify()
```

### Layer 3 — Frontend Reconnection Hook

**`frontend/hooks/useReconnectingChat.ts`** (new file)

A wrapper around `useChat` that tracks `x-job-id` and event cursor, then retries via the replay endpoint on network error.

```typescript
export function useReconnectingChat(options: UseChatOptions) {
  const jobIdRef = useRef<string | null>(null);
  const cursorRef = useRef(0);

  return useChat({
    ...options,
    onResponse(response) {
      jobIdRef.current = response.headers.get("x-job-id");
      cursorRef.current = 0;
      options.onResponse?.(response);
    },
    onFinish(message, finishOptions) {
      jobIdRef.current = null;
      cursorRef.current = 0;
      options.onFinish?.(message, finishOptions);
    },
    onError(error) {
      const jobId = jobIdRef.current;
      const cursor = cursorRef.current;
      if (jobId && cursor > 0) {
        // Reconnect to replay endpoint — useChat will re-fetch
        options.api = `/api/chat-stream/${jobId}?cursor=${cursor}`;
      }
      options.onError?.(error);
    },
  });
}
```

All components currently using `useChat` swap to `useReconnectingChat` with no other changes.

## Files Changed

| File | Change | Risk |
|------|--------|------|
| `agent/src/sse.py` | Add `id:` field + internal sequence counter | Low — additive |
| `agent/src/main.py` | Read `Last-Event-ID` header in `/api/chat` | Low — additive branch |
| `agent/src/agent_jobs.py` | Heartbeats in `_stream_from_job`, memory cap in `append_event` | Low — additive |
| `frontend/hooks/useReconnectingChat.ts` | New wrapper hook | Low — new file |
| `frontend/...` (chat components) | Swap `useChat` → `useReconnectingChat` | Low — 1-line change per component |

## What This Does Not Address

- **Redis-backed durability** — jobs still live in-memory and are lost on server restart. Acceptable: Vercel serverless doesn't restart mid-stream, and server restarts produce a clear error rather than silent data loss.
- **Backpressure signals** — TCP is sufficient. Revisit if we ever see memory pressure from concurrent batch runs.
- **Pull-based ReadableStream** — Vercel AI SDK recommends this for true backpressure. Deferred: complexity not justified until we observe actual memory issues.

## Plain English

The agent already has the equivalent of a DVR — it records every event as it streams so you can rewind and replay from any point. The problem was that when your connection dropped, nobody told the browser where the DVR was or how to ask for a rewind. This design adds three small fixes: (1) stamps every event with a number so the browser knows where it left off, (2) sends a "still alive" ping every 15 seconds so your network doesn't close the connection thinking nobody's home, and (3) adds a small client-side retry that picks up exactly where the stream dropped.
