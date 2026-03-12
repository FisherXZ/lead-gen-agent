"use client";

import type { UIMessage } from "ai";
import FileAttachment from "./FileAttachment";
import ToolPart from "./ToolPart";
import MarkdownMessage from "./MarkdownMessage";

interface ChatMessageProps {
  message: UIMessage;
  isStreaming?: boolean;
}

export default function ChatMessage({ message, isStreaming = false }: ChatMessageProps) {
  const isUser = message.role === "user";

  // Split parts into groups: consecutive text parts grouped together,
  // tool parts are individual
  const partGroups: Array<
    | { type: "text"; parts: { text: string; index: number }[] }
    | { type: "tool"; part: typeof message.parts[number]; index: number }
  > = [];

  for (let i = 0; i < message.parts.length; i++) {
    const part = message.parts[i];
    if (part.type === "text") {
      const lastGroup = partGroups[partGroups.length - 1];
      if (lastGroup && lastGroup.type === "text") {
        lastGroup.parts.push({ text: part.text, index: i });
      } else {
        partGroups.push({ type: "text", parts: [{ text: part.text, index: i }] });
      }
    } else {
      // Only treat parts as tools if they have tool indicators
      const p = part as Record<string, unknown>;
      const pType = p.type as string;
      if (pType === "dynamic-tool" || pType.startsWith("tool-") || "toolCallId" in p || "toolName" in p) {
        partGroups.push({ type: "tool", part, index: i });
      }
      // Skip non-tool, non-text parts (source-url, step-start, reasoning, file, etc.)
    }
  }

  // Find the last tool group index — text after this is "response", text before is "thinking"
  const lastToolGroupIndex = (() => {
    for (let i = partGroups.length - 1; i >= 0; i--) {
      if (partGroups[i].type === "tool") return i;
    }
    return -1; // no tools at all — everything is response
  })();

  // Find the index of the very last text part (for streaming animation)
  const lastTextIndex = (() => {
    for (let i = message.parts.length - 1; i >= 0; i--) {
      if (message.parts[i].type === "text") return i;
    }
    return -1;
  })();

  // ─── Level 1: User message ─── dark card, right-aligned
  if (isUser) {
    const fileParts = message.parts.filter(
      (p) => (p as Record<string, unknown>).type === "file"
    ) as Array<{ type: "file"; mediaType: string; filename?: string; url: string }>;
    const textParts = message.parts.filter((p) => p.type === "text");

    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl bg-slate-800 px-5 py-3 text-white shadow-sm">
          {/* File attachments */}
          {fileParts.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-2">
              {fileParts.map((fp, i) => (
                <FileAttachment
                  key={i}
                  compact
                  file={{
                    name: fp.filename || "file",
                    type: fp.mediaType || "",
                    size: 0,
                    preview: fp.mediaType?.startsWith("image/") ? fp.url : undefined,
                  }}
                />
              ))}
            </div>
          )}
          {/* Text content */}
          {textParts.map((part, i) =>
            part.type === "text" ? (
              <div key={i} className="whitespace-pre-wrap text-[15px] leading-relaxed">
                {part.text}
              </div>
            ) : null
          )}
        </div>
      </div>
    );
  }

  // ─── Assistant message ───
  return (
    <div className="space-y-2">
      {partGroups.map((group, gi) => {
        if (group.type === "text") {
          const isThinking = lastToolGroupIndex >= 0 && gi <= lastToolGroupIndex;

          if (isThinking) {
            // ─── Thinking text ─── muted, small, left border, de-emphasized
            return (
              <div
                key={`text-${gi}`}
                className="border-l-2 border-slate-200 pl-3 py-1"
              >
                {group.parts.map((tp) => (
                  <p
                    key={tp.index}
                    className="text-[13px] leading-relaxed text-slate-400"
                  >
                    {tp.text}
                  </p>
                ))}
              </div>
            );
          }

          // ─── Response text ─── prominent, full typography, no bubble
          return (
            <div key={`text-${gi}`} className="text-slate-800 pt-1">
              {group.parts.map((tp) => (
                <MarkdownMessage
                  key={tp.index}
                  content={tp.text}
                  isStreaming={isStreaming && tp.index === lastTextIndex}
                />
              ))}
            </div>
          );
        }

        // ─── Tool calls ─── compact, muted, subordinate
        const toolPart = group.part as Record<string, unknown>;
        const partType = toolPart.type as string;
        const toolCallId = (toolPart.toolCallId as string) || String(group.index);
        const toolName = (toolPart.toolName as string)
          || (partType.startsWith("tool-") ? partType.slice(5) : null)
          || "unknown";
        const partState = toolPart.state as string | undefined;
        return (
          <ToolPart
            key={toolCallId}
            toolInvocation={{
              toolCallId,
              toolName,
              state: (partState === "input-streaming" || partState === "input-available" || partState === "call" || partState === "partial-call") ? "call" : "result",
              input: toolPart.input as Record<string, unknown> | undefined,
              output: "output" in toolPart ? (toolPart.output as unknown) : undefined,
            }}
          />
        );
      })}
    </div>
  );
}
