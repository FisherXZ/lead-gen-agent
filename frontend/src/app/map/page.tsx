import { createClient } from "@/lib/supabase/server";
import ProjectMapLoader from "@/components/epc/ProjectMapLoader";

export const revalidate = 3600;

export default async function MapPage() {
  const supabase = await createClient();

  const { data: projects, error: projectsError } = await supabase
    .from("projects")
    .select("*")
    .not("latitude", "is", null)
    .order("lead_score", { ascending: false })
    .limit(10000);

  const { data: discoveries, error: discoveriesError } = await supabase
    .from("epc_discoveries")
    .select("*")
    .order("created_at", { ascending: false });

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
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Project Map</h1>
        <p className="mt-1 text-sm text-slate-500">
          Solar projects from ISO queues — geocoded to county centroids
        </p>
      </div>
      <ProjectMapLoader
        projects={projects || []}
        discoveries={discoveries || []}
      />
    </main>
  );
}
