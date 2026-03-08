import { createClient } from "@/lib/supabase/server";
import { Suspense } from "react";
import Dashboard from "@/components/Dashboard";
import EpcDiscoveryDashboard from "@/components/epc/EpcDiscoveryDashboard";
import PipelineTabs from "@/components/PipelineTabs";

export const revalidate = 3600;

export default async function PipelinePage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>;
}) {
  const { tab } = await searchParams;
  const activeTab = tab || "projects";

  const supabase = await createClient();

  const [projectsResult, discoveriesResult, runsResult] = await Promise.all([
    supabase
      .from("projects")
      .select("*", { count: "exact" })
      .order("lead_score", { ascending: false })
      .limit(10000),
    supabase
      .from("epc_discoveries")
      .select("*")
      .order("created_at", { ascending: false }),
    supabase
      .from("scrape_runs")
      .select("*")
      .eq("status", "success")
      .order("completed_at", { ascending: false })
      .limit(3),
  ]);

  if (projectsResult.error) {
    return (
      <main className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <p className="text-red-600">
          Failed to load projects: {projectsResult.error.message}
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Pipeline</h1>
        <p className="mt-1 text-sm text-slate-500">
          Utility-scale solar projects from ISO interconnection queues
        </p>
      </div>

      <Suspense>
        <PipelineTabs />
      </Suspense>

      {activeTab === "epc" ? (
        <EpcDiscoveryDashboard
          projects={projectsResult.data || []}
          discoveries={discoveriesResult.data || []}
        />
      ) : (
        <Dashboard
          initialProjects={projectsResult.data || []}
          lastRuns={runsResult.data || []}
        />
      )}
    </main>
  );
}
