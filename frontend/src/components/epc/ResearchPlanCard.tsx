"use client";

import { useState } from "react";

/* ------------------------------------------------------------------ */
/*  Lightweight markdown plan parser → structured sections             */
/* ------------------------------------------------------------------ */

interface PlanSection {
  heading: string;
  lines: string[];
}

function parsePlan(raw: string): { title: string; sections: PlanSection[] } {
  const lines = raw.split("\n");
  let title = "";
  const sections: PlanSection[] = [];
  let current: PlanSection | null = null;

  for (const line of lines) {
    const trimmed = line.trim();

    // ## Top-level title
    if (/^##\s+/.test(trimmed) && !title) {
      title = trimmed.replace(/^##\s+/, "");
      continue;
    }

    // ### Section heading
    if (/^###\s+/.test(trimmed)) {
      if (current) sections.push(current);
      current = { heading: trimmed.replace(/^###\s+/, ""), lines: [] };
      continue;
    }

    // Content lines go into the current section
    if (current && trimmed) {
      current.lines.push(trimmed);
    }
  }
  if (current) sections.push(current);

  return { title, sections };
}

/* Render inline markdown: **bold** */
function renderInline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (/^\*\*(.+)\*\*$/.test(part)) {
      return (
        <strong key={i} className="font-semibold text-slate-900">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

/* Render a content line (bullet, numbered, or plain) */
function renderLine(line: string, idx: number) {
  // Bullet: - text or * text
  const bulletMatch = line.match(/^[-*]\s+(.+)/);
  if (bulletMatch) {
    return (
      <li key={idx} className="flex gap-2 text-sm leading-relaxed text-slate-600">
        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-300" />
        <span>{renderInline(bulletMatch[1])}</span>
      </li>
    );
  }

  // Numbered: 1. text
  const numMatch = line.match(/^(\d+)\.\s+(.+)/);
  if (numMatch) {
    return (
      <li key={idx} className="flex gap-2.5 text-sm leading-relaxed text-slate-600">
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-slate-900 text-[10px] font-bold text-white">
          {numMatch[1]}
        </span>
        <span className="pt-0.5">{renderInline(numMatch[2])}</span>
      </li>
    );
  }

  // Plain text
  return (
    <p key={idx} className="text-sm leading-relaxed text-slate-600">
      {renderInline(line)}
    </p>
  );
}

/* ------------------------------------------------------------------ */
/*  Section — collapsible block with heading                           */
/* ------------------------------------------------------------------ */

const SECTION_ICONS: Record<string, React.ReactNode> = {
  know: (
    <svg className="h-4 w-4 text-amber-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 18v-5.25m0 0a6.01 6.01 0 001.5-.189m-1.5.189a6.01 6.01 0 01-1.5-.189m3.75 7.478a12.06 12.06 0 01-4.5 0m3.75 2.383a14.406 14.406 0 01-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 10-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" />
    </svg>
  ),
  challenge: (
    <svg className="h-4 w-4 text-amber-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
    </svg>
  ),
  plan: (
    <svg className="h-4 w-4 text-amber-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 6.75h12M8.25 12h12m-12 5.25h12M3.75 6.75h.007v.008H3.75V6.75zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zM3.75 12h.007v.008H3.75V12zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm-.375 5.25h.007v.008H3.75v-.008zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z" />
    </svg>
  ),
};

function getSectionIcon(heading: string): React.ReactNode {
  const lower = heading.toLowerCase();
  if (lower.includes("know") || lower.includes("context")) return SECTION_ICONS.know;
  if (lower.includes("challenge") || lower.includes("risk")) return SECTION_ICONS.challenge;
  if (lower.includes("plan") || lower.includes("step") || lower.includes("approach")) return SECTION_ICONS.plan;
  return SECTION_ICONS.plan;
}

function PlanSection({
  section,
  defaultOpen,
}: {
  section: PlanSection;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="border-b border-slate-100 last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-4 py-3 text-left transition-colors hover:bg-slate-50"
      >
        {getSectionIcon(section.heading)}
        <span className="flex-1 text-sm font-medium text-slate-800">
          {section.heading}
        </span>
        <svg
          className={`h-4 w-4 text-slate-400 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={2}
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
        </svg>
      </button>
      {open && (
        <ul className="flex flex-col gap-2 px-4 pb-4 pl-10">
          {section.lines.map((line, i) => renderLine(line, i))}
        </ul>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main card                                                          */
/* ------------------------------------------------------------------ */

export default function ResearchPlanCard({
  plan,
  isResearching,
  onApprove,
  onCancel,
}: {
  plan: string;
  isResearching: boolean;
  onApprove: () => void;
  onCancel: () => void;
}) {
  const { title, sections } = parsePlan(plan);

  // If parsing didn't produce sections, fall back to a simple display
  const hasStructure = sections.length > 0;

  return (
    <div className="max-w-2xl overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      {/* Header */}
      <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-full bg-amber-100">
            <svg className="h-3.5 w-3.5 text-amber-600" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m5.231 13.481L15 17.25m-4.5-15H5.625c-.621 0-1.125.504-1.125 1.125v16.5c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9zm3.75 11.625a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
            </svg>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
              Research Plan
            </p>
            {title && (
              <p className="text-sm font-medium text-slate-800">{title}</p>
            )}
          </div>
        </div>
      </div>

      {/* Sections */}
      {hasStructure ? (
        <div className="divide-y divide-slate-100">
          {sections.map((section, i) => (
            <PlanSection
              key={i}
              section={section}
              defaultOpen={
                // Default: open the last section (the actual plan steps)
                i === sections.length - 1
              }
            />
          ))}
        </div>
      ) : (
        /* Fallback for unstructured plans */
        <div className="px-4 py-3">
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-600">
            {plan}
          </p>
        </div>
      )}

      {/* Footer — action buttons */}
      <div className="flex items-center gap-2 border-t border-slate-200 bg-slate-50 px-4 py-3">
        {!isResearching ? (
          <>
            <button
              onClick={onApprove}
              className="inline-flex items-center gap-1.5 rounded-md bg-slate-900 px-4 py-2 text-xs font-medium text-white transition-colors hover:bg-slate-800"
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
              Approve & Run
            </button>
            <button
              onClick={onCancel}
              className="rounded-md border border-slate-200 bg-white px-4 py-2 text-xs font-medium text-slate-500 transition-colors hover:bg-slate-50"
            >
              Cancel
            </button>
          </>
        ) : (
          <span className="inline-flex items-center gap-2 text-xs text-slate-500">
            <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Running research...
          </span>
        )}
      </div>
    </div>
  );
}
