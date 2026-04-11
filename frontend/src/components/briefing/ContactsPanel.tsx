// frontend/src/components/briefing/ContactsPanel.tsx
"use client";

import { useState } from "react";
import Link from "next/link";
import { agentFetch } from "@/lib/agent-fetch";

export interface NeedContactsItem {
  discovery_id: string;
  entity_id: string;
  epc_contractor: string;
  project_name: string;
  project_id: string;
}

export interface CrmReadyItem {
  discovery_id: string;
  project_id: string;
  epc_contractor: string;
  project_name: string;
  contact_count: number;
}

interface ContactsPanelProps {
  needContacts: NeedContactsItem[];
  crmReady: CrmReadyItem[];
}

export default function ContactsPanel({
  needContacts: initialNeedContacts,
  crmReady: initialCrmReady,
}: ContactsPanelProps) {
  const [needContacts] =
    useState<NeedContactsItem[]>(initialNeedContacts);
  const [crmReady] = useState<CrmReadyItem[]>(initialCrmReady);
  const [findingId, setFindingId] = useState<string | null>(null);
  const [pushingId, setPushingId] = useState<string | null>(null);
  const [syncedIds, setSyncedIds] = useState<Set<string>>(new Set());
  const [foundIds, setFoundIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  async function handleFindContacts(entityId: string, discoveryId: string) {
    setFindingId(discoveryId);
    setError(null);
    try {
      const res = await agentFetch("/api/contacts/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entity_id: entityId }),
      });
      if (res.ok) {
        setFoundIds((prev) => new Set(prev).add(discoveryId));
      } else {
        setError("Contact discovery failed.");
      }
    } catch {
      setError("Contact discovery failed.");
    } finally {
      setFindingId(null);
    }
  }

  async function handlePushToHubSpot(projectId: string, discoveryId: string) {
    setPushingId(discoveryId);
    setError(null);
    try {
      const res = await agentFetch("/api/hubspot/push", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId }),
      });
      if (res.ok) {
        setSyncedIds((prev) => new Set(prev).add(discoveryId));
      } else {
        setError("HubSpot push failed.");
      }
    } catch {
      setError("HubSpot push failed.");
    } finally {
      setPushingId(null);
    }
  }

  const totalCount = needContacts.length + crmReady.length;

  return (
    <div className="rounded-lg border border-border-subtle bg-surface-raised">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
        <div className="flex items-center gap-2">
          <h2 className="text-[10px] font-medium uppercase tracking-widest text-text-tertiary">
            Contacts
          </h2>
          {totalCount > 0 && (
            <span className="rounded-full bg-accent-amber-muted px-2 py-0.5 text-[10px] font-semibold text-accent-amber">
              {totalCount}
            </span>
          )}
        </div>
        <Link
          href="/actions"
          className="text-[10px] text-text-tertiary transition-colors hover:text-text-secondary"
        >
          View all contacts & CRM →
        </Link>
      </div>

      {/* Error */}
      {error && (
        <div className="border-b border-border-subtle px-4 py-2">
          <p className="text-xs text-status-red">{error}</p>
        </div>
      )}

      {/* Cards */}
      <div className="divide-y divide-border-subtle">
        {totalCount === 0 ? (
          <div className="px-4 py-8 text-center">
            <p className="text-xs text-text-tertiary">
              No contacts needed right now.
            </p>
          </div>
        ) : (
          <>
            {/* CRM-ready items first */}
            {crmReady.map((item) => {
              const isSynced = syncedIds.has(item.discovery_id);
              const isPushing = pushingId === item.discovery_id;

              return (
                <div
                  key={`crm-${item.discovery_id}`}
                  className="flex items-start justify-between px-4 py-3 transition-colors hover:bg-surface-overlay"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-serif text-[13px] text-text-primary">
                        {item.epc_contractor}
                      </span>
                      <span className="rounded-full bg-accent-amber/15 px-2 py-0.5 text-[10px] font-semibold text-accent-amber">
                        {item.contact_count} contacts
                      </span>
                    </div>
                    <p className="mt-0.5 text-[10px] text-text-tertiary">
                      {item.project_name} · Ready for CRM push
                    </p>
                  </div>

                  <div className="ml-3 shrink-0">
                    {isSynced ? (
                      <span className="rounded-md bg-status-green/15 px-3 py-1 text-xs font-medium text-status-green">
                        Synced
                      </span>
                    ) : (
                      <button
                        onClick={() =>
                          handlePushToHubSpot(
                            item.project_id,
                            item.discovery_id
                          )
                        }
                        disabled={isPushing}
                        className="rounded-md bg-accent-amber px-3 py-1 text-xs font-medium text-surface-primary transition-colors hover:bg-accent-amber/90 disabled:opacity-50"
                      >
                        {isPushing ? (
                          <span className="flex items-center gap-1.5">
                            <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-surface-primary border-t-transparent" />
                            Pushing
                          </span>
                        ) : (
                          "Push to HS"
                        )}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}

            {/* Need contacts items */}
            {needContacts.map((item) => {
              const isFound = foundIds.has(item.discovery_id);
              const isFinding = findingId === item.discovery_id;

              return (
                <div
                  key={`find-${item.discovery_id}`}
                  className="flex items-start justify-between px-4 py-3 transition-colors hover:bg-surface-overlay"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-serif text-[13px] text-text-primary">
                        {item.epc_contractor}
                      </span>
                      <span className="rounded-full bg-surface-overlay px-2 py-0.5 text-[10px] font-medium text-text-tertiary">
                        0 contacts
                      </span>
                    </div>
                    <p className="mt-0.5 text-[10px] text-text-tertiary">
                      {item.project_name}
                    </p>
                  </div>

                  <div className="ml-3 shrink-0">
                    {isFound ? (
                      <span className="rounded-md bg-status-green/15 px-3 py-1 text-xs font-medium text-status-green">
                        Found
                      </span>
                    ) : (
                      <button
                        onClick={() =>
                          handleFindContacts(item.entity_id, item.discovery_id)
                        }
                        disabled={isFinding || findingId !== null}
                        className="rounded-md bg-accent-amber-muted px-3 py-1 text-xs font-medium text-accent-amber transition-colors hover:bg-accent-amber/25 disabled:opacity-50"
                      >
                        {isFinding ? (
                          <span className="flex items-center gap-1.5">
                            <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-accent-amber border-t-transparent" />
                            Finding
                          </span>
                        ) : (
                          "Find"
                        )}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}
