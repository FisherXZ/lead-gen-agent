"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport, type UIMessage } from "ai";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { agentFetch, agentHeaders, AGENT_API_URL } from "@/lib/agent-fetch";
import ChatMessage from "./ChatMessage";
import FileAttachment from "./FileAttachment";
import Playbook from "./Playbook";

const ACCEPTED_FILE_TYPES = [
  "image/png", "image/jpeg", "image/gif", "image/webp",
  "application/pdf",
  "text/plain", "text/csv", "text/markdown",
];
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB
const MAX_FILES = 5;

interface PendingFile {
  id: string;
  file: File;
  name: string;
  type: string;
  size: number;
  preview?: string; // data URL for images
  base64?: string;  // base64 data (no prefix)
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      // Strip "data:...;base64," prefix
      resolve(result.split(",")[1]);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}


interface Conversation {
  id: string;
  title: string | null;
  updated_at: string;
}

interface ChatInterfaceProps {
  initialContext?: string;
}

export default function ChatInterface({ initialContext }: ChatInterfaceProps) {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const reconnectAbortRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Use a ref so the transport body closure always reads the latest value
  const conversationIdRef = useRef<string | null>(null);
  useEffect(() => {
    conversationIdRef.current = conversationId;
  }, [conversationId]);

  // Track the current job ID for potential reconnection
  const jobIdRef = useRef<string | null>(null);

  // Stable transport — body uses a resolver function so it reads the ref each time
  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api: `${AGENT_API_URL}/api/chat`,
        body: () => ({ conversation_id: conversationIdRef.current }),
        fetch: async (url, init) => {
          const headers = new Headers(init?.headers);
          const authHdrs = await agentHeaders();
          for (const [k, v] of Object.entries(authHdrs)) {
            headers.set(k, v);
          }
          const res = await globalThis.fetch(url, { ...init, headers });
          const id = res.headers.get("x-conversation-id");
          if (id) {
            conversationIdRef.current = id;
            setConversationId(id);
            loadConversations();
          }
          const jid = res.headers.get("x-job-id");
          if (jid) jobIdRef.current = jid;
          return res;
        },
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const { messages, sendMessage, status, setMessages, stop } = useChat({ transport });

  const isLoading = status === "submitted" || status === "streaming" || reconnecting;

  // Listen for GuidanceCard button clicks to populate chat input
  useEffect(() => {
    function handlePopulate(e: Event) {
      const detail = (e as CustomEvent).detail;
      if (detail?.text) setInputValue(detail.text);
    }
    window.addEventListener("populate-chat-input", handlePopulate);
    return () => window.removeEventListener("populate-chat-input", handlePopulate);
  }, []);

  // Listen for batch cancel requests from BatchStopButton
  useEffect(() => {
    function handleCancelBatch() {
      const cid = conversationIdRef.current;
      if (!cid) return;
      agentFetch(`/api/conversations/${cid}/cancel-batch`, {
        method: "POST",
      }).catch(() => {
        // best-effort
      });
    }
    window.addEventListener("cancel-batch", handleCancelBatch);
    return () => window.removeEventListener("cancel-batch", handleCancelBatch);
  }, []);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Load conversation list
  const loadConversations = useCallback(async () => {
    try {
      const res = await agentFetch("/api/conversations");
      if (res.ok) {
        const data = await res.json();
        setConversations(data);
        return data as Conversation[];
      }
    } catch {
      // silently fail
    }
    return [];
  }, []);

  // On mount: load conversations and resume the most recent one,
  // or auto-send initialContext if provided
  const initialContextRef = useRef(initialContext);
  useEffect(() => {
    if (initialContextRef.current) {
      // Start a new conversation with the pre-loaded context
      sendMessage({ text: initialContextRef.current });
      initialContextRef.current = undefined;
    } else {
      loadConversations().then((convs) => {
        if (convs.length > 0) {
          loadConversation(convs[0].id);
        }
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load a past conversation, and reconnect if an agent job is still running
  async function loadConversation(id: string) {
    // Stop any active useChat stream (prevents conv A's events leaking into conv B)
    stop();
    // Cancel any existing reconnection stream
    reconnectAbortRef.current?.abort();
    setReconnecting(false);
    // Clear stale job ID from previous conversation
    jobIdRef.current = null;

    try {
      const res = await agentFetch(
        `/api/conversations/${id}/messages`
      );
      if (!res.ok) return;
      const data = await res.json();

      const loaded: UIMessage[] = data.map(
        (m: { id: string; role: string; content: string; parts?: unknown[] }) => ({
          id: m.id,
          role: m.role as "user" | "assistant",
          parts:
            m.parts && m.parts.length > 0
              ? m.parts
              : [{ type: "text" as const, text: m.content }],
        })
      );

      setMessages(loaded);
      setConversationId(id);
      conversationIdRef.current = id;
      setSidebarOpen(false);

      // Check if an agent job is still running for this conversation
      try {
        const statusRes = await agentFetch(
          `/api/conversations/${id}/status`
        );
        if (statusRes.ok) {
          const statusData = await statusRes.json();
          if (statusData.active_job_id) {
            reconnectToJob(statusData.active_job_id);
          }
        }
      } catch {
        // Status check failed — not critical
      }
    } catch {
      // silently fail
    }
  }

  // Reconnect to a running agent job's SSE stream
  async function reconnectToJob(jobId: string) {
    jobIdRef.current = jobId;
    const abort = new AbortController();
    reconnectAbortRef.current = abort;
    setReconnecting(true);

    try {
      const res = await agentFetch(
        `/api/chat-stream/${jobId}?cursor=0`,
        { signal: abort.signal }
      );
      if (!res.ok || !res.body) {
        setReconnecting(false);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let textAccum = "";
      const parts: Array<{ type: string; [key: string]: unknown }> = [];
      const msgId = `reconnect-${jobId}`;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6).trim();
          if (payload === "[DONE]") continue;

          try {
            const evt = JSON.parse(payload);
            if ((evt.type === "text-delta" || evt.type === "thinking-delta") && evt.delta) {
              textAccum += evt.delta;
            } else if (evt.type === "tool-input-available") {
              const existingPart = parts.find(
                (p) => p.type === "tool-invocation" && p.toolCallId === evt.toolCallId
              );
              if (existingPart) {
                // Re-emitted with enriched input (e.g. _batch_id) — update in place
                existingPart.input = evt.input;
              } else {
                parts.push({
                  type: "tool-invocation",
                  toolCallId: evt.toolCallId,
                  toolName: evt.toolName,
                  state: "partial-call",
                  input: evt.input,
                });
              }
            } else if (evt.type === "tool-output-available") {
              const existing = parts.find(
                (p) =>
                  p.type === "tool-invocation" &&
                  p.toolCallId === evt.toolCallId
              );
              if (existing) {
                existing.state = "result";
                existing.output = evt.output;
              }
            }
          } catch {
            // Ignore unparseable lines
          }
        }

        // Build a live UIMessage from accumulated events
        const liveParts: Array<{ type: string; [key: string]: unknown }> = [];
        if (textAccum) liveParts.push({ type: "text", text: textAccum });
        liveParts.push(...parts);

        if (liveParts.length > 0) {
          setMessages((prev) => {
            const withoutReconnect = prev.filter((m) => m.id !== msgId);
            return [
              ...withoutReconnect,
              {
                id: msgId,
                role: "assistant" as const,
                parts: liveParts,
              } as UIMessage,
            ];
          });
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
    } finally {
      setReconnecting(false);
      reconnectAbortRef.current = null;
      // Reload messages from DB to get the final persisted version
      try {
        const convId = conversationIdRef.current;
        if (convId) {
          const res = await agentFetch(
            `/api/conversations/${convId}/messages`
          );
          if (res.ok) {
            const data = await res.json();
            const loaded: UIMessage[] = data.map(
              (m: {
                id: string;
                role: string;
                content: string;
                parts?: unknown[];
              }) => ({
                id: m.id,
                role: m.role as "user" | "assistant",
                parts:
                  m.parts && m.parts.length > 0
                    ? m.parts
                    : [{ type: "text" as const, text: m.content }],
              })
            );
            setMessages(loaded);
          }
        }
      } catch {
        // Best effort reload
      }
    }
  }

  // Start a new conversation
  function handleNewConversation() {
    stop();
    reconnectAbortRef.current?.abort();
    setReconnecting(false);
    setMessages([]);
    setConversationId(null);
    conversationIdRef.current = null;
    jobIdRef.current = null;
    setSidebarOpen(false);
  }

  // Handle suggested prompt click
  function handlePromptSelect(prompt: string) {
    setInputValue(prompt);
  }

  // Stop the running agent job for THIS conversation only
  async function handleStop() {
    // Stop the useChat stream (frontend-only, scoped to this component)
    stop();
    // Cancel reconnection if active
    reconnectAbortRef.current?.abort();
    setReconnecting(false);

    // Cancel the backend job — try job ID first, fall back to conversation ID
    const jid = jobIdRef.current;
    const cid = conversationIdRef.current;
    if (jid) {
      try {
        await agentFetch(`/api/jobs/${jid}/cancel`, {
          method: "POST",
        });
      } catch {
        // Best effort
      }
      jobIdRef.current = null;
    } else if (cid) {
      // Fallback: user hit stop before response headers arrived (no job ID yet)
      try {
        await agentFetch(
          `/api/conversations/${cid}/cancel`,
          { method: "POST" }
        );
      } catch {
        // Best effort
      }
    }
  }

  // --- File handling ---
  async function addFiles(files: FileList | File[]) {
    const newFiles: PendingFile[] = [];
    for (const file of Array.from(files)) {
      if (pendingFiles.length + newFiles.length >= MAX_FILES) break;
      if (!ACCEPTED_FILE_TYPES.includes(file.type)) continue;
      if (file.size > MAX_FILE_SIZE) continue;

      const base64 = await fileToBase64(file);
      const pf: PendingFile = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        file,
        name: file.name,
        type: file.type,
        size: file.size,
        base64,
      };
      // Generate preview for images
      if (file.type.startsWith("image/")) {
        pf.preview = URL.createObjectURL(file);
      }
      newFiles.push(pf);
    }
    setPendingFiles((prev) => [...prev, ...newFiles].slice(0, MAX_FILES));
  }

  function removeFile(id: string) {
    setPendingFiles((prev) => {
      const removed = prev.find((f) => f.id === id);
      if (removed?.preview) URL.revokeObjectURL(removed.preview);
      return prev.filter((f) => f.id !== id);
    });
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    setIsDragOver(true);
  }
  function handleDragLeave(e: React.DragEvent) {
    e.preventDefault();
    setIsDragOver(false);
  }
  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files.length > 0) {
      addFiles(e.dataTransfer.files);
    }
  }

  function handlePaste(e: React.ClipboardEvent) {
    const items = e.clipboardData.items;
    const files: File[] = [];
    for (const item of Array.from(items)) {
      if (item.kind === "file") {
        const file = item.getAsFile();
        if (file) files.push(file);
      }
    }
    if (files.length > 0) {
      e.preventDefault();
      addFiles(files);
    }
  }

  // Handle form submit
  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = inputValue.trim();
    if ((!text && pendingFiles.length === 0) || isLoading) return;

    // Build files array using AI SDK's FileUIPart format
    const files = pendingFiles.map((pf) => ({
      type: "file" as const,
      mediaType: pf.type,
      filename: pf.name,
      url: `data:${pf.type};base64,${pf.base64}`,
    }));

    if (files.length > 0) {
      sendMessage({ text: text || "Please analyze the attached file(s).", files });
    } else {
      sendMessage({ text });
    }

    // Clean up
    setInputValue("");
    pendingFiles.forEach((pf) => {
      if (pf.preview) URL.revokeObjectURL(pf.preview);
    });
    setPendingFiles([]);
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
      {/* Sidebar */}
      <div
        className={`shrink-0 border-r border-border-subtle bg-surface-primary transition-all ${
          sidebarOpen ? "w-64" : "w-0"
        } overflow-hidden`}
      >
        <div className="flex h-full w-64 flex-col">
          <div className="border-b border-border-subtle p-3">
            <button
              onClick={handleNewConversation}
              className="w-full rounded-md bg-accent-amber px-3 py-2 text-sm font-medium text-surface-primary transition-colors hover:bg-accent-amber/90"
            >
              New conversation
            </button>
          </div>
          <div className="flex-1 overflow-y-auto">
            {conversations.map((c) => (
              <button
                key={c.id}
                onClick={() => loadConversation(c.id)}
                className={`w-full border-b border-border-subtle px-3 py-2.5 text-left transition-colors hover:bg-surface-overlay ${
                  conversationId === c.id ? "bg-accent-amber-muted" : ""
                }`}
              >
                <p className="truncate text-sm text-text-primary">
                  {c.title || "Untitled"}
                </p>
                <p className="text-xs text-text-tertiary">
                  {new Date(c.updated_at).toLocaleDateString()}
                </p>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main chat area */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-border-subtle bg-surface-raised px-4 py-3">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="rounded-md p-1.5 text-text-tertiary transition-colors hover:bg-surface-overlay hover:text-text-primary"
            title="Toggle conversations"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>
          <h2 className="text-sm font-medium text-text-primary">
            Solarina
          </h2>
        </div>

        {/* Messages — drop zone */}
        <div
          className={`flex-1 overflow-y-auto px-4 py-6 transition-colors ${isDragOver ? "bg-accent-amber-muted ring-2 ring-inset ring-accent-amber/30" : ""}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center">
              <Playbook onSelect={handlePromptSelect} />
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-4">
              {messages.map((m, idx) => (
                <ChatMessage
                  key={m.id}
                  message={m}
                  isStreaming={
                    status === "streaming" &&
                    m.role === "assistant" &&
                    idx === messages.length - 1
                  }
                />
              ))}
              {/* Thinking indicator */}
              {(status === "submitted" || (reconnecting && messages.length > 0 && messages[messages.length - 1]?.role !== "assistant")) && (
                <div className="flex items-center gap-2 py-2">
                  <div className="flex items-center gap-1">
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-text-tertiary" style={{ animationDelay: "0ms" }} />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-text-tertiary" style={{ animationDelay: "150ms" }} />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-text-tertiary" style={{ animationDelay: "300ms" }} />
                  </div>
                  <span className="text-[13px] text-text-tertiary">Thinking...</span>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input */}
        <div className="border-t border-border-subtle bg-surface-raised px-4 py-3">
          {/* File attachment chips */}
          {pendingFiles.length > 0 && (
            <div className="mx-auto mb-2 flex max-w-3xl flex-wrap gap-2">
              {pendingFiles.map((pf) => (
                <FileAttachment
                  key={pf.id}
                  file={pf}
                  onRemove={() => removeFile(pf.id)}
                />
              ))}
            </div>
          )}

          <form
            onSubmit={handleSubmit}
            className="mx-auto flex max-w-3xl items-center gap-2"
          >
            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept={ACCEPTED_FILE_TYPES.join(",")}
              className="hidden"
              onChange={(e) => {
                if (e.target.files) addFiles(e.target.files);
                e.target.value = "";
              }}
            />

            {/* Attach button */}
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={isLoading || pendingFiles.length >= MAX_FILES}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border-default bg-surface-raised text-text-tertiary transition-colors hover:bg-surface-overlay hover:text-text-primary disabled:opacity-40"
              title="Attach file (PDF, image, text)"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" />
              </svg>
            </button>

            <input
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onPaste={handlePaste}
              placeholder={pendingFiles.length > 0 ? "Add a message about your files..." : "Ask about solar projects or EPC contractors..."}
              className="h-10 flex-1 rounded-lg border border-border-default bg-surface-overlay px-4 text-sm text-text-primary placeholder:text-text-tertiary focus:border-border-focus focus:outline-none focus:ring-1 focus:ring-border-focus"
              disabled={isLoading}
            />
            {isLoading ? (
              <button
                type="button"
                onClick={handleStop}
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent-amber text-surface-primary transition-colors hover:bg-accent-amber/90"
                title="Stop generating"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                  <rect x="6" y="6" width="12" height="12" rx="2" />
                </svg>
              </button>
            ) : (
              <button
                type="submit"
                disabled={!inputValue.trim() && pendingFiles.length === 0}
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent-amber text-surface-primary transition-colors hover:bg-accent-amber/90 disabled:opacity-50"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              </button>
            )}
          </form>
        </div>
      </div>
    </div>
  );
}
