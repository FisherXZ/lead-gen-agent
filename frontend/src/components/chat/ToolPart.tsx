"use client";

import ProjectListCard from "./parts/ProjectListCard";
import EpcResultCard from "./parts/EpcResultCard";
import BatchProgressCard from "./parts/BatchProgressCard";
import DiscoveryListCard from "./parts/DiscoveryListCard";
import GuidanceCard from "./parts/GuidanceCard";
import CsvCard from "./parts/CsvCard";
import PdfCard from "./parts/PdfCard";
import ProgressNotificationCard from "./parts/ProgressNotificationCard";
import DiscoveryApprovalCard from "./parts/DiscoveryApprovalCard";
import CollapsibleToolCard from "./CollapsibleToolCard";
import { EpcSource } from "@/lib/types";
import ToolIcon from "./ToolIcon";

interface ToolInvocation {
  toolCallId: string;
  toolName: string;
  state: "partial-call" | "call" | "result";
  input?: Record<string, unknown>;
  output?: unknown;
}

interface PdfCardData {
  url?: string;
  text?: string;
  length?: number;
  content_type?: string;
  page_count?: number;
  pages_extracted?: number;
  error?: string;
}

interface ToolPartProps {
  toolInvocation: ToolInvocation;
}

function deriveStatus(
  state: string,
  output: unknown
): "running" | "done" | "error" {
  if (state !== "result") return "running";
  if (output && typeof output === "object" && "error" in output) return "error";
  return "done";
}

function getProgressLabel(toolName: string, input?: Record<string, unknown>): string {
  const labels: Record<string, string | ((inp?: Record<string, unknown>) => string)> = {
    web_search: (inp) => `Searching "${inp?.query || "..."}"`,
    web_search_broad: (inp) => `Searching "${inp?.query || "..."}"`,
    fetch_page: (inp) => {
      try {
        const url = String(inp?.url || "");
        return `Reading ${new URL(url).hostname}`;
      } catch {
        return "Reading page...";
      }
    },
    search_projects: "Searching projects...",
    search_projects_with_epc: "Searching projects with EPC...",
    query_knowledge_base: (inp) => `Looking up "${inp?.entity_name || "..."}"`,
    report_findings: "Reporting findings...",
    research_epc: "Researching EPC contractor...",
    remember: "Saving to memory...",
    recall: "Recalling memories...",
    request_guidance: "Asking for your input...",
    request_discovery_review: "Presenting finding for review...",
    approve_discovery: (inp) =>
      inp?.action === "rejected" ? "Rejecting discovery..." : "Approving discovery...",
    notify_progress: (inp) => {
      const stage = String(inp?.stage || "").replace("_", " ");
      return inp?.message ? `${stage}: ${inp.message}` : `Progress: ${stage}`;
    },
    research_scratchpad: (inp) =>
      inp?.operation === "read" ? "Reading scratchpad..." : "Saving to scratchpad...",
    get_discoveries: "Loading discoveries...",
    batch_research_epc: "Running batch research...",
    export_csv: "Generating CSV...",
  };

  const entry = labels[toolName];
  if (typeof entry === "function") return entry(input);
  if (typeof entry === "string") return entry;
  return `Running ${toolName}...`;
}

function getDoneLabel(
  toolName: string,
  input?: Record<string, unknown>,
  output?: unknown
): string {
  const data = (output && typeof output === "object" ? output : {}) as Record<string, unknown>;

  switch (toolName) {
    case "web_search":
      return `Searched "${input?.query || "web"}"`;
    case "web_search_broad":
      return `Searched "${input?.query || "web"}"`;
    case "fetch_page": {
      const isPdf = data.content_type === "pdf";
      try {
        const host = new URL(String(input?.url || "")).hostname;
        return isPdf
          ? `Read PDF from ${host} (${data.page_count ?? "?"} pages)`
          : `Read ${host}`;
      } catch {
        return isPdf ? "Read PDF" : "Read page";
      }
    }
    case "search_projects": {
      const count = Array.isArray(data.projects) ? data.projects.length : (data.count ?? "?");
      return `Found ${count} projects`;
    }
    case "search_projects_with_epc": {
      const count = Array.isArray(data.projects) ? data.projects.length : (data.count ?? "?");
      return `Found ${count} projects with EPC data`;
    }
    case "query_knowledge_base":
      return `Looked up "${input?.entity_name || "entity"}"`;
    case "report_findings": {
      const disc = data.discovery as Record<string, unknown> | undefined;
      return `Reported: ${disc?.epc_contractor || "findings"}`;
    }
    case "research_epc": {
      const disc = data.discovery as Record<string, unknown> | undefined;
      return `Researched EPC${disc?.epc_contractor ? `: ${disc.epc_contractor}` : ""}`;
    }
    case "remember":
      return "Saved to memory";
    case "recall": {
      const memories = Array.isArray(data.memories) ? data.memories : [];
      return `Recalled ${memories.length} memor${memories.length === 1 ? "y" : "ies"}`;
    }
    case "request_guidance":
      return "Asked for your input";
    case "request_discovery_review":
      return data.epc_contractor
        ? `Review: ${data.epc_contractor} (${data.confidence || "unknown"})`
        : "Discovery ready for review";
    case "approve_discovery":
      return data.status === "accepted"
        ? `Accepted: ${data.epc_contractor || "discovery"}`
        : data.status === "rejected"
          ? "Discovery rejected"
          : "Processing review...";
    case "notify_progress": {
      const stage = String(input?.stage || "").replace("_", " ");
      return data.message ? `${stage}: ${data.message}` : `Progress: ${stage}`;
    }
    case "research_scratchpad":
      return data.key ? `Scratchpad: ${data.key}` : "Scratchpad updated";
    case "get_discoveries": {
      const discoveries = Array.isArray(data.discoveries) ? data.discoveries : [];
      const count = data.count ?? discoveries.length;
      return `Loaded ${count} discoveries`;
    }
    case "batch_research_epc": {
      const completed = data.completed ?? "?";
      const total = data.total ?? "?";
      return `Batch research: ${completed}/${total}`;
    }
    case "export_csv": {
      const rowCount = data.row_count ?? "?";
      return `Exported ${rowCount} rows to ${data.filename || "CSV"}`;
    }
    default:
      return `Completed: ${toolName}`;
  }
}

/** Tools that should show expanded body when done */
const EXPAND_WHEN_DONE = new Set([
  "search_projects",
  "search_projects_with_epc",
  "report_findings",
  "research_epc",
  "batch_research_epc",
  "get_discoveries",
  "request_guidance",
  "request_discovery_review",
  "approve_discovery",
  "export_csv",
]);

/** Tools that should show expanded body while running (live progress) */
const EXPAND_WHILE_RUNNING = new Set(["batch_research_epc"]);

function shouldDefaultExpand(toolName: string, state: string, output?: unknown): boolean {
  if (EXPAND_WHILE_RUNNING.has(toolName)) return true;
  if (state !== "result") return false;
  if (EXPAND_WHEN_DONE.has(toolName)) return true;
  // Auto-expand fetch_page when it returns a PDF
  if (toolName === "fetch_page" && output && typeof output === "object" && "content_type" in output) {
    return (output as Record<string, unknown>).content_type === "pdf";
  }
  return false;
}

function renderToolBody(
  toolName: string,
  output: unknown,
  input?: Record<string, unknown>,
  isLive?: boolean,
): React.ReactNode | null {
  const data = (output && typeof output === "object" ? output : {}) as Record<string, unknown>;

  switch (toolName) {
    case "search_projects":
    case "search_projects_with_epc":
      return <ProjectListCard data={data} />;

    case "research_epc":
    case "report_findings":
      return <EpcResultCard data={data} />;

    case "batch_research_epc":
      return <BatchProgressCard data={data} isLive={isLive} input={input} />;

    case "get_discoveries":
      return <DiscoveryListCard data={data} />;

    case "recall": {
      const memories = Array.isArray(data.memories) ? data.memories : [];
      if (memories.length === 0) return null;
      return (
        <ul className="space-y-1 px-3 py-2">
          {memories.map((m: unknown, i: number) => {
            const mem = m as Record<string, unknown>;
            return (
              <li key={i} className="text-sm text-slate-600">
                &bull; {String(mem.content || mem.text || JSON.stringify(m))}
              </li>
            );
          })}
        </ul>
      );
    }

    case "request_guidance":
      return <GuidanceCard data={data as { status_summary?: string; question?: string; options?: string[]; awaiting_response?: boolean; error?: string }} />;

    case "notify_progress":
      return <ProgressNotificationCard data={data as { stage?: string; message?: string; detail?: string }} />;

    case "request_discovery_review":
      return <DiscoveryApprovalCard data={data as { discovery_id?: string; epc_contractor?: string; confidence?: string; sources?: EpcSource[]; source_summary?: string[]; assessment?: string; awaiting_review?: boolean; status?: string; message?: string; error?: string }} />;

    case "approve_discovery": {
      const status = data.status as string;
      const epc = data.epc_contractor as string;
      if (status === "accepted") {
        return (
          <div className="px-3 py-2">
            <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold text-emerald-700">
              Confirmed: {epc}
            </span>
          </div>
        );
      }
      if (status === "rejected") {
        return (
          <div className="px-3 py-2 text-sm text-slate-500">
            Rejected{data.reason ? `: ${data.reason}` : ""}
          </div>
        );
      }
      return null;
    }

    case "fetch_page": {
      if (data.content_type === "pdf") {
        return <PdfCard data={data as PdfCardData} />;
      }
      return null;
    }

    case "export_csv":
      return <CsvCard data={data as { headers?: string[]; rows?: string[][]; csv_text?: string; filename?: string; row_count?: number; error?: string }} />;

    // These tools have no expanded body
    case "web_search":
    case "web_search_broad":
    case "remember":
    case "query_knowledge_base":
      return null;

    default:
      return null;
  }
}

export default function ToolPart({ toolInvocation }: ToolPartProps) {
  const { toolName, state, input, output } = toolInvocation;
  const status = deriveStatus(state, output);
  const label =
    status === "running"
      ? getProgressLabel(toolName, input)
      : getDoneLabel(toolName, input, output);
  const expanded = shouldDefaultExpand(toolName, state, output);

  // For batch_research_epc: show live card during call state, final card on result
  const isLiveBatch =
    toolName === "batch_research_epc" && state !== "result";
  const body =
    state === "result" && output
      ? renderToolBody(toolName, output, input)
      : isLiveBatch
        ? renderToolBody(toolName, {}, input, true)
        : null;

  return (
    <CollapsibleToolCard
      icon={<ToolIcon toolName={toolName} />}
      label={label}
      status={status}
      defaultExpanded={expanded}
    >
      {body}
    </CollapsibleToolCard>
  );
}
