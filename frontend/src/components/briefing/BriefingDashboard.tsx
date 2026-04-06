// frontend/src/components/briefing/BriefingDashboard.tsx
"use client";

import { useState, useCallback } from "react";
import PipelineFunnel from "./PipelineFunnel";
import QuickNav from "./QuickNav";
import NeedsReviewPanel, { PendingDiscovery } from "./NeedsReviewPanel";
import NeedsInvestigationPanel, {
  UnresearchedProject,
} from "./NeedsInvestigationPanel";
import ContactsPanel, {
  NeedContactsItem,
  CrmReadyItem,
} from "./ContactsPanel";
import RecentlyCompletedPanel, {
  CompletedItem,
} from "./RecentlyCompletedPanel";

export interface BriefingDashboardProps {
  funnel: {
    totalProjects: number;
    researched: number;
    pendingReview: number;
    accepted: number;
    inCrm: number;
  };
  pendingDiscoveries: PendingDiscovery[];
  totalPending: number;
  unresearchedProjects: UnresearchedProject[];
  totalUnresearched: number;
  needContacts: NeedContactsItem[];
  crmReady: CrmReadyItem[];
  recentlyCompleted: CompletedItem[];
}

export default function BriefingDashboard({
  funnel: initialFunnel,
  pendingDiscoveries,
  totalPending,
  unresearchedProjects,
  totalUnresearched,
  needContacts,
  crmReady,
  recentlyCompleted,
}: BriefingDashboardProps) {
  const [funnel, setFunnel] = useState(initialFunnel);

  const handleReviewCountChange = useCallback((delta: number) => {
    setFunnel((prev) => ({
      ...prev,
      pendingReview: Math.max(0, prev.pendingReview + delta),
      accepted: prev.accepted - delta, // approve decreases pending, increases accepted
    }));
  }, []);

  return (
    <div className="space-y-5">
      {/* Pipeline Funnel */}
      <PipelineFunnel
        totalProjects={funnel.totalProjects}
        researched={funnel.researched}
        pendingReview={funnel.pendingReview}
        accepted={funnel.accepted}
        inCrm={funnel.inCrm}
      />

      {/* Quick Nav */}
      <QuickNav />

      {/* 2x2 Action Grid */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <NeedsReviewPanel
          discoveries={pendingDiscoveries}
          totalPending={totalPending}
          onCountChange={handleReviewCountChange}
        />
        <NeedsInvestigationPanel
          projects={unresearchedProjects}
          totalUnresearched={totalUnresearched}
        />
        <ContactsPanel needContacts={needContacts} crmReady={crmReady} />
        <RecentlyCompletedPanel items={recentlyCompleted} />
      </div>
    </div>
  );
}
