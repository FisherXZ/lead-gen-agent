"use client";

import { useState } from "react";

export default function SourceInfoPanel() {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative inline-block">
      <button
        onClick={() => setOpen((v) => !v)}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-slate-300 text-[10px] font-bold text-slate-400 hover:border-slate-400 hover:text-slate-600 transition-colors"
        title="How We Source Data"
        aria-expanded={open}
      >
        i
      </button>

      {open && (
        <div className="absolute left-0 top-6 z-20 w-80 rounded-lg border border-slate-200 bg-white p-4 shadow-lg">
          <div className="mb-2 flex items-center justify-between">
            <h4 className="text-sm font-semibold text-slate-900">
              How We Source Data
            </h4>
            <button
              onClick={() => setOpen(false)}
              className="text-slate-400 hover:text-slate-600"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <ul className="space-y-2 text-xs text-slate-600">
            <li>
              <span className="font-medium text-slate-800">Brave Web Search</span>
              {" "}&mdash; Broad web search across news, blogs, regulatory PDFs, and niche solar industry sites.
            </li>
            <li>
              <span className="font-medium text-slate-800">Tavily Deep Search</span>
              {" "}&mdash; AI-powered deep search optimized for extracting structured information from web pages.
            </li>
            <li>
              <span className="font-medium text-slate-800">Direct Page Fetch</span>
              {" "}&mdash; Full-page reading of specific URLs (press releases, portfolio pages, filings) for detailed extraction.
            </li>
            <li>
              <span className="font-medium text-slate-800">ISO Queue Filing</span>
              {" "}&mdash; Data extracted directly from ISO interconnection queue records (CAISO, ERCOT, MISO).
            </li>
            <li>
              <span className="font-medium text-slate-800">Knowledge Base</span>
              {" "}&mdash; Prior research results and known developer-EPC relationships from our internal database.
            </li>
          </ul>

          <p className="mt-3 border-t border-slate-100 pt-2 text-[11px] text-slate-400">
            LinkedIn sources are treated as lowest reliability and are never sufficient alone. All findings are subject to human review.
          </p>
        </div>
      )}
    </div>
  );
}
