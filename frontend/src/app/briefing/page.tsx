// frontend/src/app/briefing/page.tsx
import { createClient } from "@/lib/supabase/server";
import BriefingDashboard from "@/components/briefing/BriefingDashboard";
import type { PendingDiscovery } from "@/components/briefing/NeedsReviewPanel";
import type { UnresearchedProject } from "@/components/briefing/NeedsInvestigationPanel";
import type { NeedContactsItem, CrmReadyItem } from "@/components/briefing/ContactsPanel";
import type { CompletedItem } from "@/components/briefing/RecentlyCompletedPanel";

export const revalidate = 300; // 5 minute ISR

export default async function BriefingPage() {
  const supabase = await createClient();

  // ─── Parallel data fetch ─────────────────────────────────────────────
  const [
    projectCountResult,
    pendingResult,
    acceptedResult,
    allDiscoveriesCountResult,
    hubspotSyncResult,
  ] = await Promise.all([
    // 1. Total projects count
    supabase.from("projects").select("*", { count: "exact", head: true }),

    // 2. Pending discoveries (for review panel + funnel count)
    supabase
      .from("epc_discoveries")
      .select(
        "id, epc_contractor, confidence, reasoning, project_id, projects(id, project_name, mw_capacity, iso_region)"
      )
      .eq("review_status", "pending")
      .order("created_at", { ascending: false })
      .limit(5),

    // 3. Accepted discoveries (for contacts, completed, funnel)
    supabase
      .from("epc_discoveries")
      .select(
        "id, epc_contractor, confidence, entity_id, project_id, review_status, created_at, projects(id, project_name, mw_capacity, iso_region, state, lead_score)"
      )
      .eq("review_status", "accepted")
      .order("created_at", { ascending: false })
      .limit(50),

    // 4. All discoveries count (for "researched" funnel stage)
    supabase
      .from("epc_discoveries")
      .select("project_id", { count: "exact", head: true }),

    // 5. HubSpot sync log (for funnel + completed panel)
    supabase
      .from("hubspot_sync_log")
      .select("project_id, created_at")
      .order("created_at", { ascending: false })
      .limit(100),
  ]);

  // ─── Error handling ──────────────────────────────────────────────────
  if (projectCountResult.error) {
    return (
      <main className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <p className="text-status-red">
          Failed to load data: {projectCountResult.error.message}
        </p>
      </main>
    );
  }

  // ─── Derive funnel counts ────────────────────────────────────────────
  const totalProjects = projectCountResult.count ?? 0;
  const pendingDiscoveriesRaw = pendingResult.data || [];
  const acceptedDiscoveries = acceptedResult.data || [];
  const hubspotSyncs = hubspotSyncResult.data || [];
  const hubspotProjectIds = new Set(hubspotSyncs.map((s: any) => s.project_id));

  // For a more accurate pending count, do a separate count query
  const pendingCountResult = await supabase
    .from("epc_discoveries")
    .select("*", { count: "exact", head: true })
    .eq("review_status", "pending");
  const totalPendingCount = pendingCountResult.count ?? pendingDiscoveriesRaw.length;

  // Accepted count
  const acceptedCountResult = await supabase
    .from("epc_discoveries")
    .select("*", { count: "exact", head: true })
    .eq("review_status", "accepted");
  const acceptedCount = acceptedCountResult.count ?? acceptedDiscoveries.length;

  // Researched = distinct project_id count from epc_discoveries
  const researchedResult = await supabase.rpc("count_distinct_projects_discovered");
  // Fallback: use allDiscoveriesCountResult count if RPC doesn't exist
  const researched =
    typeof researchedResult.data === "number"
      ? researchedResult.data
      : allDiscoveriesCountResult.count ?? 0;

  const inCrm = new Set(hubspotSyncs.map((s: any) => s.project_id)).size;

  const funnel = {
    totalProjects,
    researched,
    pendingReview: totalPendingCount,
    accepted: acceptedCount,
    inCrm,
  };

  // ─── Build panel data ────────────────────────────────────────────────

  // Panel 1: Needs Review (top 5 pending)
  const pendingDiscoveries: PendingDiscovery[] = pendingDiscoveriesRaw.map(
    (d: any) => {
      const p = d.projects as any;
      const reasoningSummary =
        typeof d.reasoning === "string"
          ? d.reasoning.slice(0, 200)
          : d.reasoning?.summary?.slice(0, 200) ?? "";
      return {
        id: d.id,
        epc_contractor: d.epc_contractor,
        confidence: d.confidence,
        reasoning_summary: reasoningSummary,
        project_id: d.project_id,
        project_name: p?.project_name || "Unknown Project",
        mw_capacity: p?.mw_capacity ?? null,
        iso_region: p?.iso_region || "—",
      };
    }
  );

  // Panel 2: Needs Investigation (unresearched projects, top 5 by lead_score)
  // Fetch all discovered project IDs for accurate filtering
  const allDiscoveredResult = await supabase
    .from("epc_discoveries")
    .select("project_id");
  const allDiscoveredIds = new Set(
    (allDiscoveredResult.data || []).map((d: any) => d.project_id)
  );

  const unresearchedResult = await supabase
    .from("projects")
    .select("id, project_name, iso_region, state, lead_score")
    .not("id", "in", `(${[...allDiscoveredIds].join(",")})`)
    .order("lead_score", { ascending: false })
    .limit(5);

  const unresearchedProjects: UnresearchedProject[] = (
    unresearchedResult.data || []
  ).map((p: any) => ({
    id: p.id,
    project_name: p.project_name || "Unnamed Project",
    iso_region: p.iso_region,
    state: p.state,
    lead_score: p.lead_score ?? 0,
  }));

  const totalUnresearched = totalProjects - allDiscoveredIds.size;

  // Panel 3: Contacts
  // Need contacts: accepted discoveries with entity_id but 0 contacts
  const entitiesWithContacts = new Set<string>();
  if (acceptedDiscoveries.some((d: any) => d.entity_id)) {
    const entityIds = acceptedDiscoveries
      .filter((d: any) => d.entity_id)
      .map((d: any) => d.entity_id);
    const contactsResult = await supabase
      .from("contacts")
      .select("entity_id")
      .in("entity_id", entityIds);
    (contactsResult.data || []).forEach((c: any) =>
      entitiesWithContacts.add(c.entity_id)
    );
  }

  const needContacts: NeedContactsItem[] = acceptedDiscoveries
    .filter(
      (d: any) => d.entity_id && !entitiesWithContacts.has(d.entity_id)
    )
    .slice(0, 5)
    .map((d: any) => {
      const p = d.projects as any;
      return {
        discovery_id: d.id,
        entity_id: d.entity_id,
        epc_contractor: d.epc_contractor,
        project_name: p?.project_name || "Unknown Project",
        project_id: d.project_id,
      };
    });

  // CRM-ready: accepted with entity that HAS contacts but NOT in hubspot_sync_log
  const crmReady: CrmReadyItem[] = [];
  const entitiesWithContactsList = acceptedDiscoveries.filter(
    (d: any) =>
      d.entity_id &&
      entitiesWithContacts.has(d.entity_id) &&
      !hubspotProjectIds.has(d.project_id)
  );
  // Get contact counts for CRM-ready items
  for (const d of entitiesWithContactsList.slice(0, 3)) {
    const countResult = await supabase
      .from("contacts")
      .select("*", { count: "exact", head: true })
      .eq("entity_id", (d as any).entity_id);
    const p = (d as any).projects as any;
    crmReady.push({
      discovery_id: (d as any).id,
      project_id: (d as any).project_id,
      epc_contractor: (d as any).epc_contractor,
      project_name: p?.project_name || "Unknown Project",
      contact_count: countResult.count ?? 0,
    });
  }

  // Panel 4: Recently Completed (accepted discoveries, most recent)
  const recentlyCompleted: CompletedItem[] = acceptedDiscoveries
    .slice(0, 5)
    .map((d: any) => {
      const p = d.projects as any;
      const contactCount = entitiesWithContacts.has(d.entity_id) ? 1 : 0; // Approximate
      return {
        discovery_id: d.id,
        project_id: d.project_id,
        epc_contractor: d.epc_contractor,
        project_name: p?.project_name || "Unknown Project",
        mw_capacity: p?.mw_capacity ?? null,
        contact_count: contactCount,
        has_hubspot_sync: hubspotProjectIds.has(d.project_id),
        completed_at: d.created_at,
      };
    });

  // ─── Render ──────────────────────────────────────────────────────────
  return (
    <main className="mx-auto max-w-7xl px-4 pt-12 pb-16 sm:px-6 lg:px-8">
      <div className="mb-8">
        <h1 className="font-serif text-3xl tracking-tight text-text-primary">
          Briefing
        </h1>
        <p className="mt-1 text-sm text-text-tertiary">
          Your command center for leads, reviews, and pipeline actions.
        </p>
      </div>

      <BriefingDashboard
        funnel={funnel}
        pendingDiscoveries={pendingDiscoveries}
        totalPending={totalPendingCount}
        unresearchedProjects={unresearchedProjects}
        totalUnresearched={totalUnresearched}
        needContacts={needContacts}
        crmReady={crmReady}
        recentlyCompleted={recentlyCompleted}
      />
    </main>
  );
}
