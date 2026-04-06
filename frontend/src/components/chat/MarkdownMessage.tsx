"use client";

import { useRef } from "react";
import { Streamdown } from "streamdown";
import { code } from "@streamdown/code";
import "streamdown/styles.css";
import CitationBadge from "./CitationBadge";

interface MarkdownMessageProps {
  content: string;
  isStreaming: boolean;
}

const plugins = { code };

/** Check if a URL looks like an external source (not internal/relative) */
function isExternalUrl(href: string): boolean {
  try {
    const url = new URL(href);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

export default function MarkdownMessage({
  content,
  isStreaming,
}: MarkdownMessageProps) {
  const citationCounterRef = useRef(0);

  // Reset counter on each render (citations re-number per message render)
  citationCounterRef.current = 0;

  const components = {
    table: ({ children, ...props }: React.ComponentProps<"table">) => (
      <div className="overflow-x-auto my-2 rounded-lg border border-border-subtle">
        <table {...props} className="min-w-full">
          {children}
        </table>
      </div>
    ),
    a: ({ children, href, ...props }: React.ComponentProps<"a">) => {
      // Convert external links to citation badges
      if (href && isExternalUrl(href)) {
        citationCounterRef.current += 1;
        return (
          <CitationBadge href={href} index={citationCounterRef.current}>
            {children}
          </CitationBadge>
        );
      }
      // Keep internal/relative links as normal
      return (
        <a {...props} href={href} target="_blank" rel="noopener noreferrer">
          {children}
        </a>
      );
    },
  };

  if (!content || content.trim() === "") {
    return null;
  }

  return (
    <div className="prose prose-invert max-w-none prose-headings:font-serif prose-headings:font-semibold prose-headings:text-text-primary prose-p:text-text-secondary prose-p:leading-relaxed prose-strong:text-text-primary prose-a:text-accent-amber prose-a:no-underline hover:prose-a:underline prose-code:rounded prose-code:bg-surface-overlay prose-code:px-1 prose-code:py-0.5 prose-code:text-sm prose-code:text-text-secondary prose-code:before:content-none prose-code:after:content-none prose-pre:bg-surface-overlay prose-pre:rounded-lg prose-th:text-left prose-th:font-medium prose-th:text-text-secondary prose-th:border prose-th:border-border-subtle prose-th:px-3 prose-td:text-text-secondary prose-td:border prose-td:border-border-subtle prose-td:px-3 prose-td:py-1.5 prose-th:py-1.5 prose-li:text-text-secondary">
      <Streamdown
        animated
        plugins={plugins}
        components={components}
        isAnimating={isStreaming}
      >
        {content}
      </Streamdown>
    </div>
  );
}
