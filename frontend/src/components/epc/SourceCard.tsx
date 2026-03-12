"use client";

import { EpcSource } from "@/lib/types";

interface SourceCardProps {
  source: EpcSource;
}

const SOURCE_METHOD_LABELS: Record<string, string> = {
  brave_search: "Brave Web Search",
  tavily_search: "Tavily Deep Search",
  page_fetch: "Direct Page Fetch",
  iso_filing: "ISO Queue Filing",
  knowledge_base: "Knowledge Base",
};

const CHANNEL_LABELS: Record<string, string> = {
  developer_pr: "Developer PR",
  trade_publication: "Trade Publication",
  permit_filing: "Permit Filing",
  regulatory_filing: "Regulatory Filing",
  news_article: "News Article",
  company_website: "Company Website",
  sec_filing: "SEC Filing",
  linkedin: "LinkedIn",
  conference: "Conference",
};

const RELIABILITY_COLORS: Record<string, string> = {
  high: "bg-emerald-400",
  medium: "bg-amber-400",
  low: "bg-red-400",
};

function formatChannelLabel(channel: string): string {
  return (
    CHANNEL_LABELS[channel] ||
    channel
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

function getSourceLink(source: EpcSource): {
  href: string;
  label: string;
} | null {
  const url = source.url;

  // Case 1: Normal URL — only allow http(s) to prevent XSS via javascript: URIs
  if (url && !url.startsWith("search:")) {
    if (url.startsWith("http://") || url.startsWith("https://")) {
      return { href: url, label: "View source" };
    }
    // Non-http URL (e.g. javascript:) — treat as no URL
    return null;
  }

  // Case 2: URL starts with "search:" — Google search link
  if (url && url.startsWith("search:")) {
    const query = url.slice("search:".length);
    return {
      href: `https://www.google.com/search?q=${encodeURIComponent(query)}`,
      label: "Search for source",
    };
  }

  // Case 3: No URL but search_query exists
  if (!url && source.search_query) {
    return {
      href: `https://www.google.com/search?q=${encodeURIComponent(source.search_query)}`,
      label: "Search for source",
    };
  }

  return null;
}

export default function SourceCard({ source }: SourceCardProps) {
  const reliabilityColor =
    RELIABILITY_COLORS[source.reliability] || RELIABILITY_COLORS.low;

  const link = getSourceLink(source);

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div>
            <span className="text-sm font-medium text-slate-900">
              {formatChannelLabel(source.channel)}
            </span>
            {source.source_method && (
              <span className="ml-1 text-xs text-slate-400">
                via {SOURCE_METHOD_LABELS[source.source_method] || source.source_method}
              </span>
            )}
          </div>
          <span
            className={`inline-block h-2 w-2 rounded-full ${reliabilityColor}`}
            title={`${source.reliability} reliability`}
          />
        </div>
        {source.date && (
          <span className="text-xs text-slate-400">{source.date}</span>
        )}
      </div>

      {source.publication && (
        <p className="mb-1 text-xs font-medium text-slate-500">
          {source.publication}
        </p>
      )}

      <p className="text-sm leading-relaxed text-slate-600">
        {source.excerpt}
      </p>

      {link && (
        <a
          href={link.href}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-block text-xs font-medium text-blue-600 hover:text-blue-800"
        >
          {link.label}
        </a>
      )}
    </div>
  );
}
