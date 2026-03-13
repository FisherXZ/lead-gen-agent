"use client";

import { useEffect, useState } from "react";
import ReviewQueue from "@/components/epc/ReviewQueue";
import { PendingDiscoveryWithProject } from "@/lib/types";
import { agentFetch } from "@/lib/agent-fetch";
import { useAuth } from "@/lib/auth";

export default function ReviewPage() {
  const { user, loading: authLoading } = useAuth();
  const [discoveries, setDiscoveries] = useState<PendingDiscoveryWithProject[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (authLoading || !user) return;
    agentFetch("/api/discoveries/pending")
      .then((res) => (res.ok ? res.json() : []))
      .then(setDiscoveries)
      .catch(() => setDiscoveries([]))
      .finally(() => setLoading(false));
  }, [authLoading, user]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold font-serif text-text-primary">Review Queue</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Review pending EPC discoveries before they are promoted to the knowledge base.
        </p>
      </div>
      {loading ? (
        <div className="rounded-lg border border-border-subtle bg-surface-raised p-12 text-center">
          <p className="text-sm text-text-tertiary">Loading...</p>
        </div>
      ) : (
        <ReviewQueue initialDiscoveries={discoveries} />
      )}
    </div>
  );
}
