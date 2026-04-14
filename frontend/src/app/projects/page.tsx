import { createClient } from "@/lib/supabase/server";
import { Project, EpcDiscovery } from "@/lib/types";
import EpcDiscoveryDashboard from "@/components/epc/EpcDiscoveryDashboard";

export const revalidate = 3600;

export default async function ProjectsPage() {
  const supabase = await createClient();

  const { data: projects } = await supabase
    .from("projects")
    .select("*")
    .order("queue_date", { ascending: false });

  const { data: discoveries } = await supabase
    .from("epc_discoveries")
    .select("*")
    .order("created_at", { ascending: false });

  return (
    <main className="mx-auto max-w-7xl px-4 pt-12 pb-16 sm:px-6 lg:px-8">
      <div className="mb-8">
        <h1 className="font-serif text-3xl tracking-tight text-text-primary">
          Pipeline
        </h1>
        <p className="mt-1 text-sm text-text-tertiary">
          All projects, sortable and filterable. Research EPCs inline.
        </p>
      </div>

      <EpcDiscoveryDashboard
        projects={(projects ?? []) as Project[]}
        discoveries={(discoveries ?? []) as EpcDiscovery[]}
      />
    </main>
  );
}
