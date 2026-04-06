"use client";

import type { UIMessage } from "ai";
import FileAttachment from "./FileAttachment";
import ToolPart from "./ToolPart";
import MarkdownMessage from "./MarkdownMessage";
import ResearchTimeline from "./ResearchTimeline";
import SourceSummaryBar from "./SourceSummaryBar";

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
        <div className="max-w-[80%] rounded-2xl bg-surface-overlay px-5 py-3 text-text-primary">
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

  // ─── Helper: render a single tool group as a ToolPart ───
  function renderToolPart(group: { type: "tool"; part: typeof message.parts[number]; index: number }) {
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
  }

  // ─── Determine if we should use timeline mode ───
  const toolGroups = partGroups.filter((g) => g.type === "tool") as Array<{
    type: "tool";
    part: typeof message.parts[number];
    index: number;
  }>;
  const hasNotifyProgress = toolGroups.some((g) => {
    const tp = g.part as Record<string, unknown>;
    return (tp.toolName as string) === "notify_progress";
  });
  const useTimeline = toolGroups.length >= 2 || hasNotifyProgress;

  // ─── Build timeline stages if in timeline mode ───
  function buildTimelineStages() {
    // Separate thinking, tool, and response groups
    const thinkingGroups: Array<{ type: "text"; parts: { text: string; index: number }[] }> = [];
    const responseGroups: Array<{ type: "text"; parts: { text: string; index: number }[] }> = [];
    const toolSequence: Array<{
      type: "tool";
      part: typeof message.parts[number];
      index: number;
    }> = [];

    for (const group of partGroups) {
      if (group.type === "text") {
        responseGroups.push(group);
      } else {
        toolSequence.push(group);
      }
    }

    // Group tools between notify_progress markers into stages
    type Stage = {
      name: string;
      status: "pending" | "active" | "complete" | "error";
      tools: typeof toolSequence;
    };
    const stages: Stage[] = [];

    if (hasNotifyProgress) {
      let currentStage: Stage | null = null;
      for (const tg of toolSequence) {
        const tp = tg.part as Record<string, unknown>;
        const toolName = (tp.toolName as string) || "";
        if (toolName === "notify_progress") {
          const input = tp.input as Record<string, unknown> | undefined;
          const stageName = (input?.stage as string) || "research";
          currentStage = { name: stageName, status: "pending", tools: [] };
          stages.push(currentStage);
        } else {
          if (!currentStage) {
            currentStage = { name: "research", status: "pending", tools: [] };
            stages.push(currentStage);
          }
          currentStage.tools.push(tg);
        }
      }
    } else {
      // Single "Research" stage for all tools
      stages.push({ name: "research", status: "pending", tools: toolSequence });
    }

    // Compute stage statuses
    for (const stage of stages) {
      const states = stage.tools.map((tg) => {
        const tp = tg.part as Record<string, unknown>;
        const s = tp.state as string | undefined;
        const output = tp.output as Record<string, unknown> | undefined;
        if (s === "result" && output && "error" in output) return "error";
        if (s === "result") return "done";
        return "running";
      });

      if (states.length === 0) {
        stage.status = "pending";
      } else if (states.every((s) => s === "done")) {
        stage.status = "complete";
      } else if (states.some((s) => s === "error") && states.every((s) => s === "error" || s === "done")) {
        stage.status = "error";
      } else if (states.some((s) => s === "running")) {
        stage.status = "active";
      } else {
        stage.status = "pending";
      }
    }

    return { thinkingGroups, responseGroups, stages };
  }

  // ─── Assistant message: Timeline mode ───
  if (useTimeline) {
    const { thinkingGroups, responseGroups, stages } = buildTimelineStages();

    const timelineStages = stages.map((stage) => ({
      name: stage.name,
      status: stage.status,
      children: stage.tools.map((tg) => renderToolPart(tg)),
    }));

    return (
      <div className="space-y-2">
        {/* Research timeline */}
        <ResearchTimeline stages={timelineStages} />

        {/* Source summary bar — between timeline and response */}
        <SourceSummaryBar message={message} />

        {/* Response text */}
        {responseGroups.map((group, gi) => (
          <div key={`response-${gi}`} className="text-text-primary pt-1">
            {group.parts.map((tp) => (
              <MarkdownMessage
                key={tp.index}
                content={tp.text}
                isStreaming={isStreaming && tp.index === lastTextIndex}
              />
            ))}
          </div>
        ))}
      </div>
    );
  }

  // ─── Assistant message: Flat mode (0-1 tools) ───
  return (
    <div className="space-y-2">
      {partGroups.map((group, gi) => {
        if (group.type === "text") {
          return (
            <div key={`text-${gi}`} className="text-text-primary pt-1">
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

        return renderToolPart(group);
      })}
    </div>
  );
}
