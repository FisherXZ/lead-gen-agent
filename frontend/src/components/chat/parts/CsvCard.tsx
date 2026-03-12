"use client";

import { useState } from "react";

interface CsvCardProps {
  data: {
    headers?: string[];
    rows?: string[][];
    csv_text?: string;
    filename?: string;
    row_count?: number;
    error?: string;
  };
}

const MAX_PREVIEW_ROWS = 20;

export default function CsvCard({ data }: CsvCardProps) {
  const [showAll, setShowAll] = useState(false);

  if (data.error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        CSV error: {data.error}
      </div>
    );
  }

  const headers = data.headers || [];
  const allRows = data.rows || [];
  const displayRows = showAll ? allRows : allRows.slice(0, MAX_PREVIEW_ROWS);
  const hasMore = allRows.length > MAX_PREVIEW_ROWS;

  function handleDownload() {
    if (!data.csv_text) return;
    const blob = new Blob([data.csv_text], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = data.filename || "export.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="bg-white p-4">
      {/* Header bar */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded bg-emerald-100">
            <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="text-emerald-600">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
            </svg>
          </div>
          <div>
            <span className="text-sm font-medium text-slate-900">
              {data.filename || "export.csv"}
            </span>
            <span className="ml-2 text-xs text-slate-500">
              {data.row_count ?? allRows.length} rows · {headers.length} columns
            </span>
          </div>
        </div>
        {data.csv_text && (
          <button
            onClick={handleDownload}
            className="flex items-center gap-1.5 rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-emerald-700"
          >
            <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            Download
          </button>
        )}
      </div>

      {/* Table */}
      {headers.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50">
                {headers.map((h, i) => (
                  <th
                    key={i}
                    className="whitespace-nowrap px-3 py-2 font-semibold text-slate-700"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {displayRows.map((row, ri) => (
                <tr key={ri} className="hover:bg-slate-50">
                  {row.map((cell, ci) => (
                    <td
                      key={ci}
                      className="max-w-[200px] truncate whitespace-nowrap px-3 py-1.5 text-slate-600"
                      title={cell}
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Show more / less */}
      {hasMore && (
        <button
          onClick={() => setShowAll(!showAll)}
          className="mt-2 text-xs font-medium text-blue-600 hover:text-blue-700"
        >
          {showAll
            ? "Show less"
            : `Show all ${allRows.length} rows (${allRows.length - MAX_PREVIEW_ROWS} more)`}
        </button>
      )}
    </div>
  );
}
