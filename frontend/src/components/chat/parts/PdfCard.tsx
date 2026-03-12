"use client";

import { useState } from "react";

interface PdfCardProps {
  data: {
    url?: string;
    text?: string;
    length?: number;
    content_type?: string;
    page_count?: number;
    pages_extracted?: number;
    error?: string;
  };
}

export default function PdfCard({ data }: PdfCardProps) {
  const [expanded, setExpanded] = useState(false);

  if (data.error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        PDF error: {data.error}
      </div>
    );
  }

  const hostname = (() => {
    try {
      return new URL(data.url || "").hostname;
    } catch {
      return "PDF";
    }
  })();

  const filename = (() => {
    try {
      const path = new URL(data.url || "").pathname;
      const segments = path.split("/").filter(Boolean);
      const last = segments[segments.length - 1] || "document.pdf";
      return decodeURIComponent(last);
    } catch {
      return "document.pdf";
    }
  })();

  return (
    <div className="bg-white p-4">
      {/* PDF header card */}
      <div className="flex items-start gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
        {/* PDF icon / thumbnail */}
        <div className="flex h-12 w-10 shrink-0 items-center justify-center rounded bg-red-100">
          <svg
            width={20}
            height={20}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            className="text-red-600"
          >
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <text
              x="12"
              y="17"
              textAnchor="middle"
              fontSize="6"
              fill="currentColor"
              stroke="none"
              fontWeight="bold"
            >
              PDF
            </text>
          </svg>
        </div>

        {/* Info */}
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-slate-900" title={filename}>
            {filename}
          </p>
          <p className="text-xs text-slate-500">
            {hostname}
            {data.page_count ? ` \u00B7 ${data.page_count} page${data.page_count !== 1 ? "s" : ""}` : ""}
            {data.pages_extracted && data.pages_extracted < (data.page_count || 0)
              ? ` (${data.pages_extracted} extracted)`
              : ""}
          </p>
        </div>

        {/* Actions */}
        <div className="flex shrink-0 gap-1.5">
          <button
            onClick={() => setExpanded(!expanded)}
            className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50"
          >
            {expanded ? "Collapse" : "View text"}
          </button>
          {data.url && (
            <a
              href={data.url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50"
            >
              Open
            </a>
          )}
        </div>
      </div>

      {/* Expanded text */}
      {expanded && data.text && (
        <div className="mt-3 max-h-80 overflow-y-auto rounded-lg border border-slate-200 bg-slate-900 p-4">
          <pre className="whitespace-pre-wrap text-xs leading-relaxed text-slate-200">
            {data.text}
          </pre>
        </div>
      )}
    </div>
  );
}
