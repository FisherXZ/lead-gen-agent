import { NextResponse } from "next/server";
import { createServiceClient } from "@/lib/supabase/service";

export const revalidate = 300; // 5 min ISR cache

export async function GET() {
  const supabase = createServiceClient();

  const oneWeekAgo = new Date();
  oneWeekAgo.setDate(oneWeekAgo.getDate() - 7);

  const [pendingRes, newProjectsRes, acceptedRes] = await Promise.all([
    supabase
      .from("epc_discoveries")
      .select("id", { count: "exact", head: true })
      .eq("review_status", "pending"),
    supabase
      .from("projects")
      .select("id", { count: "exact", head: true })
      .gte("created_at", oneWeekAgo.toISOString()),
    supabase
      .from("epc_discoveries")
      .select("id, entity_id, project_id")
      .eq("review_status", "accepted"),
  ]);

  const awaiting_review = pendingRes.count ?? 0;
  const new_projects_this_week = newProjectsRes.count ?? 0;

  const accepted = acceptedRes.data ?? [];
  const entityIds = [
    ...new Set(accepted.map((d) => d.entity_id).filter(Boolean)),
  ] as string[];
  const projectIds = accepted.map((d) => d.project_id).filter(Boolean);

  let epcs_need_contacts = 0;
  let leads_ready_for_crm = 0;

  if (entityIds.length > 0) {
    const { data: contactRows } = await supabase
      .from("contacts")
      .select("entity_id")
      .in("entity_id", entityIds);

    const entitiesWithContacts = new Set(
      (contactRows ?? []).map((c: { entity_id: string }) => c.entity_id)
    );

    epcs_need_contacts = entityIds.filter(
      (eid) => !entitiesWithContacts.has(eid)
    ).length;

    if (projectIds.length > 0) {
      const { data: syncRows } = await supabase
        .from("hubspot_sync_log")
        .select("project_id")
        .in("project_id", projectIds);

      const syncedProjects = new Set(
        (syncRows ?? []).map((s: { project_id: string }) => s.project_id)
      );

      leads_ready_for_crm = accepted.filter((d) => {
        if (!d.entity_id || !d.project_id) return false;
        return (
          entitiesWithContacts.has(d.entity_id) &&
          !syncedProjects.has(d.project_id)
        );
      }).length;
    }
  }

  return NextResponse.json({
    awaiting_review,
    new_projects_this_week,
    epcs_need_contacts,
    leads_ready_for_crm,
  });
}
