import ReviewQueue from "@/components/epc/ReviewQueue";
import { PendingDiscoveryWithProject } from "@/lib/types";

const AGENT_API_URL =
  process.env.NEXT_PUBLIC_AGENT_API_URL || "http://localhost:8000";

async function getPendingDiscoveries(): Promise<PendingDiscoveryWithProject[]> {
  try {
    const res = await fetch(`${AGENT_API_URL}/api/discoveries/pending`, {
      cache: "no-store",
    });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export default async function ReviewPage() {
  const discoveries = await getPendingDiscoveries();

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">Review Queue</h1>
        <p className="mt-1 text-sm text-slate-500">
          Review pending EPC discoveries before they are promoted to the knowledge base.
        </p>
      </div>
      <ReviewQueue initialDiscoveries={discoveries} />
    </div>
  );
}
