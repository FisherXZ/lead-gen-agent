import { createClient } from "@/lib/supabase/server";
import { notFound } from "next/navigation";
import Link from "next/link";
import { EpcDiscovery } from "@/lib/types";
import ResearchButton from "@/components/epc/ResearchButton";
import ReasoningCard from "@/components/epc/ReasoningCard";

export const revalidate = 3600;

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "—";
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function ConfidenceBadge({ confidence }: { confidence: string }) {
  const cls: Record<string, string> = {
    confirmed: "bg-emerald-100 text-emerald-700",
    likely: "bg-orange-100 text-orange-700",
    possible: "bg-amber-100 text-amber-700",
    unknown: "bg-slate-100 text-slate-600",
  };
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ${cls[confidence] || cls.unknown}`}
    >
      {confidence}
    </span>
  );
}

function StatusPill({ status }: { status: string | null }) {
  const s = (status || "").toLowerCase();
  let cls = "bg-slate-100 text-slate-600";
  if (s.includes("active")) cls = "bg-emerald-50 text-emerald-700";
  else if (s.includes("completed") || s.includes("done"))
    cls = "bg-emerald-100 text-emerald-700";
  else if (s.includes("withdrawn")) cls = "bg-red-50 text-red-600";

  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}
    >
      {status || "—"}
    </span>
  );
}

function InfoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between border-b border-slate-100 py-3">
      <span className="text-sm font-medium text-slate-500">{label}</span>
      <span className="text-sm text-slate-900">{children}</span>
    </div>
  );
}

export default async function ProjectDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const supabase = await createClient();

  const { data: project, error } = await supabase
    .from("projects")
    .select("*")
    .eq("id", id)
    .single();

  if (error || !project) {
    notFound();
  }

  // Fetch discoveries for this project
  const { data: discoveries } = await supabase
    .from("epc_discoveries")
    .select("*")
    .eq("project_id", id)
    .order("created_at", { ascending: false });

  const activeDiscovery = (discoveries || []).find(
    (d: EpcDiscovery) => d.review_status !== "rejected"
  );

  const hasCoordinates = project.latitude != null && project.longitude != null;

  return (
    <main className="mx-auto max-w-4xl px-4 py-10 sm:px-6 lg:px-8">
      {/* Breadcrumb */}
      <div className="mb-6">
        <Link
          href="/"
          className="text-sm text-slate-500 transition-colors hover:text-slate-700"
        >
          &larr; Back to Pipeline
        </Link>
      </div>

      {/* Header */}
      <div className="mb-8">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">
              {project.project_name || project.queue_id}
            </h1>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-slate-500">
              <span className="rounded bg-slate-100 px-2 py-0.5 font-medium text-slate-700">
                {project.iso_region}
              </span>
              {project.developer && <span>{project.developer}</span>}
              {project.mw_capacity && (
                <span>{project.mw_capacity.toLocaleString()} MW</span>
              )}
            </div>
          </div>
          <StatusPill status={project.status} />
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Project Info */}
        <div className="rounded-lg border border-slate-200 bg-white p-6">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-400">
            Project Details
          </h2>
          <div className="flex flex-col">
            <InfoRow label="Queue ID">{project.queue_id}</InfoRow>
            <InfoRow label="ISO Region">{project.iso_region}</InfoRow>
            <InfoRow label="Developer">{project.developer || "—"}</InfoRow>
            <InfoRow label="State">{project.state || "—"}</InfoRow>
            <InfoRow label="County">{project.county || "—"}</InfoRow>
            <InfoRow label="Capacity">
              {project.mw_capacity
                ? `${project.mw_capacity.toLocaleString()} MW`
                : "—"}
            </InfoRow>
            <InfoRow label="Fuel Type">{project.fuel_type || "—"}</InfoRow>
            <InfoRow label="Queue Status">
              <StatusPill status={project.status} />
            </InfoRow>
            <InfoRow label="Queue Date">{formatDate(project.queue_date)}</InfoRow>
            <InfoRow label="Expected COD">
              {formatDate(project.expected_cod)}
            </InfoRow>
            {project.epc_company && (
              <InfoRow label="EPC Company">{project.epc_company}</InfoRow>
            )}
          </div>
        </div>

        {/* Location */}
        <div className="rounded-lg border border-slate-200 bg-white p-6">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-400">
            Location
          </h2>
          <div className="flex flex-col">
            <InfoRow label="State">{project.state || "—"}</InfoRow>
            <InfoRow label="County">{project.county || "—"}</InfoRow>
            <InfoRow label="Latitude">
              {project.latitude != null ? project.latitude : "—"}
            </InfoRow>
            <InfoRow label="Longitude">
              {project.longitude != null ? project.longitude : "—"}
            </InfoRow>
          </div>
          {hasCoordinates ? (
            <a
              href={`https://www.google.com/maps?q=${project.latitude},${project.longitude}`}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-4 inline-flex items-center gap-2 rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-800"
            >
              <svg
                className="h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z"
                />
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z"
                />
              </svg>
              View on Google Maps
            </a>
          ) : (
            <p className="mt-4 text-xs text-slate-400">
              Coordinates not available for this project.
            </p>
          )}
        </div>
      </div>

      {/* EPC Discovery */}
      <div className="mt-6 rounded-lg border border-slate-200 bg-white p-6">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
            EPC Discovery
          </h2>
          <ResearchButton projectId={project.id} hasExisting={!!activeDiscovery} />
        </div>
        {activeDiscovery ? (
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-3">
              <span className="text-xl font-bold text-slate-900">
                {activeDiscovery.epc_contractor}
              </span>
              <ConfidenceBadge confidence={activeDiscovery.confidence} />
              <span
                className={`rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ${
                  activeDiscovery.review_status === "accepted"
                    ? "bg-emerald-100 text-emerald-700"
                    : activeDiscovery.review_status === "pending"
                      ? "bg-amber-100 text-amber-700"
                      : "bg-red-100 text-red-700"
                }`}
              >
                {activeDiscovery.review_status}
              </span>
            </div>

            <ReasoningCard
              reasoning={activeDiscovery.reasoning}
              sources={activeDiscovery.sources}
            />

            {activeDiscovery.tokens_used > 0 && (
              <p className="text-xs text-slate-400">
                Tokens used: {activeDiscovery.tokens_used.toLocaleString()}
              </p>
            )}
          </div>
        ) : (
          <p className="py-4 text-sm text-slate-400">
            No EPC discovery results for this project yet.
          </p>
        )}
      </div>

      {/* Data Source */}
      <div className="mt-6 rounded-lg border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-400">
          Data Source
        </h2>
        <div className="flex flex-col gap-3 text-sm">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 h-2 w-2 shrink-0 rounded-full bg-amber-400" />
            <div>
              <p className="font-medium text-slate-700">
                {project.source === "gem_tracker"
                  ? "Global Energy Monitor — GEM Tracker"
                  : `${project.iso_region} Interconnection Queue`}
              </p>
              <p className="mt-0.5 text-slate-500">
                {project.source === "gem_tracker"
                  ? "Global database of power plants tracking capacity, ownership, and development status."
                  : `Official interconnection queue data from ${project.iso_region}. Includes queue position, capacity, fuel type, developer, and expected commercial operation date.`}
              </p>
            </div>
          </div>
          {activeDiscovery && (
            <div className="flex items-start gap-3">
              <span className="mt-0.5 h-2 w-2 shrink-0 rounded-full bg-emerald-400" />
              <div>
                <p className="font-medium text-slate-700">
                  EPC Discovery Agent
                </p>
                <p className="mt-0.5 text-slate-500">
                  AI-powered research using web search across trade publications, press releases, permit filings, and regulatory documents.
                  {activeDiscovery.sources.length > 0 && (
                    <span>
                      {" "}Found {activeDiscovery.sources.length} source{activeDiscovery.sources.length !== 1 ? "s" : ""}.
                    </span>
                  )}
                </p>
              </div>
            </div>
          )}
          <p className="mt-1 text-xs text-slate-400">
            Last updated {formatDate(project.updated_at)}
          </p>
        </div>
      </div>

      {/* Raw Data (collapsible) */}
      {project.raw_data && (
        <details className="mt-6 rounded-lg border border-slate-200 bg-white">
          <summary className="cursor-pointer p-6 text-sm font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-600">
            Raw ISO Queue Data
          </summary>
          <div className="border-t border-slate-200 p-6">
            <pre className="max-h-96 overflow-auto rounded-md bg-slate-50 p-4 text-xs text-slate-600">
              {JSON.stringify(project.raw_data, null, 2)}
            </pre>
          </div>
        </details>
      )}
    </main>
  );
}
