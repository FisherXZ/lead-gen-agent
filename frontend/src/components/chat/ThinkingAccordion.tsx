"use client";

import { useState, useEffect, useRef } from "react";
import MarkdownMessage from "./MarkdownMessage";

interface ThinkingAccordionProps {
  texts: string[];
  isStreaming: boolean;
}

function Chevron({ expanded }: { expanded: boolean }) {
  return (
    <svg
      width={14}
      height={14}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`shrink-0 text-text-tertiary transition-transform duration-200 ${
        expanded ? "rotate-180" : ""
      }`}
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

export default function ThinkingAccordion({
  texts,
  isStreaming,
}: ThinkingAccordionProps) {
  const content = texts.join("\n\n");
  const [expanded, setExpanded] = useState(isStreaming);
  const [manualOverride, setManualOverride] = useState(false);
  const wasStreamingRef = useRef(isStreaming);

  // Auto-expand when streaming starts, auto-collapse when streaming stops
  // (unless user manually toggled)
  useEffect(() => {
    if (!manualOverride) {
      if (isStreaming && !wasStreamingRef.current) {
        setExpanded(true);
      } else if (!isStreaming && wasStreamingRef.current) {
        setExpanded(false);
      }
    }
    wasStreamingRef.current = isStreaming;
  }, [isStreaming, manualOverride]);

  function handleToggle() {
    setManualOverride(true);
    setExpanded((prev) => !prev);
  }

  if (!content.trim()) return null;

  return (
    <div
      className="overflow-hidden rounded-lg border border-border-subtle bg-surface-raised border-l-2 border-l-accent-amber/15"
      role="region"
      aria-label="Agent reasoning"
    >
      {/* Header */}
      <button
        onClick={handleToggle}
        aria-expanded={expanded}
        className="flex w-full items-center gap-2 px-3 py-1.5 select-none hover:bg-surface-overlay focus:outline-none focus:ring-1 focus:ring-border-focus focus:ring-inset rounded-lg"
      >
        {/* Brain icon */}
        <svg
          width={14}
          height={14}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          className="shrink-0 text-text-tertiary"
        >
          <path d="M12 2a7 7 0 0 1 7 7c0 2.38-1.19 4.47-3 5.74V17a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 0 1 7-7z" />
          <path d="M10 21h4" />
          <path d="M9 9h.01" />
          <path d="M15 9h.01" />
          <path d="M9.5 13a3.5 3.5 0 0 0 5 0" />
        </svg>

        <span
          className={`min-w-0 flex-1 text-left text-[13px] font-medium text-text-tertiary ${
            isStreaming ? "animate-thinking-pulse" : ""
          }`}
        >
          {isStreaming ? "Reasoning..." : "Reasoning"}
        </span>

        <Chevron expanded={expanded} />
      </button>

      {/* Collapsible body */}
      <div
        className="grid transition-[grid-template-rows] duration-200 ease-out"
        style={{ gridTemplateRows: expanded ? "1fr" : "0fr" }}
      >
        <div className="overflow-hidden">
          <div className="border-t border-border-subtle px-3 py-2">
            <div className="text-[13px] leading-relaxed text-text-secondary">
              <MarkdownMessage content={content} isStreaming={isStreaming} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
