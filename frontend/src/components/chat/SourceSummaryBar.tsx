"use client";

import type { UIMessage } from "ai";

interface SourceSummaryBarProps {
  message: UIMessage;
}

function extractDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

interface SourceInfo {
  domain: string;
  url: string;
}

/**
 * Walk all tool parts in a message and extract unique source URLs.
 * Sources come from: web_search results, fetch_page inputs, and KB lookups.
 */
function extractSources(message: UIMessage): SourceInfo[] {
  const seen = new Set<string>();
  const sources: SourceInfo[] = [];

  for (const part of message.parts) {
    const p = part as Record<string, unknown>;
    const toolName = p.toolName as string | undefined;
    const output = p.output as Record<string, unknown> | undefined;
    const input = p.input as Record<string, unknown> | undefined;

    if (!toolName) continue;

    // web_search / web_search_broad: extract from results array
    if ((toolName === "web_search" || toolName === "web_search_broad") && output) {
      const results = Array.isArray(output.results) ? output.results : [];
      for (const r of results as Array<Record<string, unknown>>) {
        const url = r.url as string | undefined;
        if (url) {
          const domain = extractDomain(url);
          if (!seen.has(domain)) {
            seen.add(domain);
            sources.push({ domain, url });
          }
        }
      }
    }

    // fetch_page: extract from input URL
    if (toolName === "fetch_page" && input?.url) {
      const url = input.url as string;
      const domain = extractDomain(url);
      if (!seen.has(domain)) {
        seen.add(domain);
        sources.push({ domain, url });
      }
    }
  }

  return sources;
}

const MAX_PILLS = 8;

export default function SourceSummaryBar({ message }: SourceSummaryBarProps) {
  const sources = extractSources(message);
  if (sources.length === 0) return null;

  const visible = sources.slice(0, MAX_PILLS);
  const remaining = sources.length - visible.length;

  return (
    <div className="py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-medium tracking-wide uppercase text-text-tertiary">
          Sources
        </span>
        {visible.map((s, i) => (
          <a
            key={i}
            href={s.url}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded bg-surface-overlay border border-border-subtle px-2 py-0.5 text-[12px] text-text-secondary hover:bg-accent-amber/15 transition-colors"
          >
            {s.domain}
          </a>
        ))}
        {remaining > 0 && (
          <span className="text-[11px] text-text-tertiary">
            +{remaining} more
          </span>
        )}
      </div>
    </div>
  );
}
