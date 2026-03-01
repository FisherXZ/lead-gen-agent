import { createClient } from "@/lib/supabase/server";
import Dashboard from "@/components/Dashboard";

export const revalidate = 3600; // revalidate every hour

export default async function Home() {
  const supabase = await createClient();

  const { data: projects, error: projectsError } = await supabase
    .from("projects")
    .select("*")
    .order("lead_score", { ascending: false });

  const { data: lastRuns, error: runsError } = await supabase
    .from("scrape_runs")
    .select("*")
    .eq("status", "success")
    .order("completed_at", { ascending: false })
    .limit(3);

  if (projectsError) {
    return (
      <main className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <p className="text-red-600">
          Failed to load projects: {projectsError.message}
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-900">
          Solar Lead Gen Dashboard
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Utility-scale solar projects from ISO interconnection queues
        </p>
      </div>
      <Dashboard
        initialProjects={projects || []}
        lastRuns={lastRuns || []}
      />
    </main>
  );
}
