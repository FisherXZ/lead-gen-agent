"use client";

import { useEffect, useState } from "react";
import { agentFetch } from "@/lib/agent-fetch";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";

interface Contact {
  id: string;
  full_name: string;
  title: string | null;
  linkedin_url: string | null;
  source_url: string | null;
  outreach_context: string | null;
}

interface ActionableLead {
  discovery_id: string;
  project_id: string;
  project_name: string | null;
  developer: string | null;
  mw_capacity: number | null;
  state: string | null;
  expected_cod: string | null;
  lead_score: number | null;
  epc_contractor: string;
  confidence: string;
  entity_id: string | null;
  contacts: Contact[];
  contact_count: number;
  contact_discovery_status: string | null;
  has_hubspot_sync: boolean;
}

export default function ActionsPage() {
  const { user, loading: authLoading } = useAuth();
  const [actions, setActions] = useState<ActionableLead[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [hubspotConnected, setHubspotConnected] = useState(false);
  const [pushing, setPushing] = useState<string | null>(null);
  const [discovering, setDiscovering] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading || !user) return;

    Promise.all([
      agentFetch("/api/actions").then((r) => (r.ok ? r.json() : [])),
      agentFetch("/api/hubspot/status").then((r) => (r.ok ? r.json() : { connected: false })),
    ])
      .then(([actionsData, hsStatus]) => {
        setActions(actionsData);
        setHubspotConnected(hsStatus.connected);
      })
      .catch(() => {
        setActions([]);
      })
      .finally(() => setLoading(false));
  }, [authLoading, user]);

  async function handlePush(projectId: string) {
    setPushing(projectId);
    try {
      const res = await agentFetch("/api/hubspot/push", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId }),
      });
      const data = await res.json();
      if (res.ok && data.errors?.length === 0) {
        toast.success("Pushed to HubSpot successfully");
        // Update local state
        setActions((prev) =>
          prev.map((a) =>
            a.project_id === projectId ? { ...a, has_hubspot_sync: true } : a
          )
        );
      } else {
        toast.error(data.detail || data.errors?.[0] || "Push failed");
      }
    } catch {
      toast.error("Failed to push to HubSpot");
    } finally {
      setPushing(null);
    }
  }

  async function handleDiscoverContacts(entityId: string) {
    setDiscovering(entityId);
    try {
      const res = await agentFetch("/api/contacts/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entity_id: entityId }),
      });
      if (res.ok) {
        const data = await res.json();
        toast.success(`Found ${data.contacts?.length || 0} contacts`);
        // Refresh actions
        const refreshed = await agentFetch("/api/actions").then((r) =>
          r.ok ? r.json() : actions
        );
        setActions(refreshed);
      } else {
        toast.error("Contact discovery failed");
      }
    } catch {
      toast.error("Contact discovery failed");
    } finally {
      setDiscovering(null);
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6">
        <h1 className="font-serif text-2xl font-normal tracking-tight text-text-primary">
          Sales Actions
        </h1>
        <p className="mt-1 text-sm text-text-secondary">
          Accepted discoveries with contacts, ready for outreach.
          {!hubspotConnected && (
            <span className="ml-2 text-accent-amber">
              HubSpot not connected &mdash;{" "}
              <a href="/settings" className="underline hover:text-text-primary">
                connect in Settings
              </a>
            </span>
          )}
        </p>
      </div>

      {loading ? (
        <div className="rounded-lg border border-border-subtle bg-surface-raised p-12 text-center">
          <p className="text-sm text-text-tertiary">Loading...</p>
        </div>
      ) : actions.length === 0 ? (
        <div className="rounded-lg border border-border-subtle bg-surface-raised p-12 text-center">
          <p className="text-sm text-text-tertiary">
            No actionable leads yet. Accept discoveries in the Review Queue to see them here.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {actions.map((action) => {
            const expanded = expandedId === action.discovery_id;
            return (
              <div
                key={action.discovery_id}
                className="rounded-lg border border-border-subtle bg-surface-raised transition-colors hover:border-border-default"
              >
                {/* Row header */}
                <button
                  onClick={() =>
                    setExpandedId(expanded ? null : action.discovery_id)
                  }
                  className="flex w-full items-center gap-4 px-5 py-4 text-left"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-serif text-sm font-medium text-text-primary">
                        {action.project_name || "Unnamed Project"}
                      </span>
                      {action.contact_count > 0 && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-accent-amber/15 px-2 py-0.5 text-xs font-medium text-accent-amber">
                          <svg className="h-3 w-3" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
                          </svg>
                          {action.contact_count} contacts
                        </span>
                      )}
                      {action.has_hubspot_sync && (
                        <span className="rounded-full bg-status-green/15 px-2 py-0.5 text-xs font-medium text-status-green">
                          In HubSpot
                        </span>
                      )}
                    </div>
                    <div className="mt-1 flex items-center gap-3 text-xs text-text-tertiary">
                      <span>{action.epc_contractor}</span>
                      <span>{action.state}</span>
                      <span>{action.mw_capacity}MW</span>
                      {action.lead_score && (
                        <span>Score: {action.lead_score}</span>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                    {action.contact_count === 0 && action.entity_id && (
                      <button
                        onClick={() => handleDiscoverContacts(action.entity_id!)}
                        disabled={discovering === action.entity_id || action.contact_discovery_status === "pending"}
                        className="rounded-md border border-border-default px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-surface-overlay disabled:opacity-50"
                      >
                        {action.contact_discovery_status === "pending" || discovering === action.entity_id
                          ? "Finding..."
                          : "Find Contacts"}
                      </button>
                    )}
                    {hubspotConnected && !action.has_hubspot_sync && (
                      <button
                        onClick={() => handlePush(action.project_id)}
                        disabled={pushing === action.project_id}
                        className="rounded-md bg-accent-amber px-3 py-1.5 text-xs font-medium text-surface-primary transition-colors hover:bg-accent-amber/90 disabled:opacity-50"
                      >
                        {pushing === action.project_id
                          ? "Pushing..."
                          : "Push to HubSpot"}
                      </button>
                    )}
                  </div>

                  <svg
                    className={`h-5 w-5 shrink-0 text-text-tertiary transition-transform ${
                      expanded ? "rotate-180" : ""
                    }`}
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={1.5}
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M19.5 8.25l-7.5 7.5-7.5-7.5"
                    />
                  </svg>
                </button>

                {/* Expanded details */}
                {expanded && (
                  <div className="border-t border-border-subtle px-5 py-4">
                    <div className="grid gap-4 md:grid-cols-2">
                      {/* Project info */}
                      <div>
                        <h3 className="text-xs font-medium uppercase tracking-wider text-text-tertiary">
                          Project Details
                        </h3>
                        <dl className="mt-2 space-y-1 text-sm">
                          <div className="flex gap-2">
                            <dt className="text-text-tertiary">Developer:</dt>
                            <dd className="text-text-primary">{action.developer || "—"}</dd>
                          </div>
                          <div className="flex gap-2">
                            <dt className="text-text-tertiary">Capacity:</dt>
                            <dd className="text-text-primary">{action.mw_capacity}MW</dd>
                          </div>
                          <div className="flex gap-2">
                            <dt className="text-text-tertiary">Expected COD:</dt>
                            <dd className="text-text-primary">{action.expected_cod || "—"}</dd>
                          </div>
                          <div className="flex gap-2">
                            <dt className="text-text-tertiary">EPC:</dt>
                            <dd className="text-text-primary">{action.epc_contractor} ({action.confidence})</dd>
                          </div>
                        </dl>
                      </div>

                      {/* Contacts */}
                      <div>
                        <h3 className="text-xs font-medium uppercase tracking-wider text-text-tertiary">
                          Contacts ({action.contact_count})
                        </h3>
                        {action.contacts.length > 0 ? (
                          <div className="mt-2 space-y-2">
                            {action.contacts.map((c) => (
                              <div
                                key={c.id}
                                className="rounded-md border border-border-subtle bg-surface-overlay px-3 py-2"
                              >
                                <div className="flex items-center justify-between">
                                  <span className="text-sm font-medium text-text-primary">
                                    {c.full_name}
                                  </span>
                                  {c.linkedin_url && (
                                    <a
                                      href={c.linkedin_url}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="text-xs text-accent-amber hover:underline"
                                    >
                                      LinkedIn
                                    </a>
                                  )}
                                </div>
                                {c.title && (
                                  <p className="text-xs text-text-secondary">{c.title}</p>
                                )}
                                {c.outreach_context && (
                                  <p className="mt-1 text-xs text-text-tertiary italic">
                                    {c.outreach_context}
                                  </p>
                                )}
                              </div>
                            ))}
                          </div>
                        ) : action.contact_discovery_status === "pending" ? (
                          <p className="mt-2 text-sm text-text-tertiary">
                            Finding contacts...
                          </p>
                        ) : action.contact_discovery_status === "failed" ? (
                          <p className="mt-2 text-sm text-status-red">
                            Contact discovery failed.{" "}
                            {action.entity_id && (
                              <button
                                onClick={() => handleDiscoverContacts(action.entity_id!)}
                                className="underline hover:text-text-primary"
                              >
                                Retry
                              </button>
                            )}
                          </p>
                        ) : (
                          <p className="mt-2 text-sm text-text-tertiary">
                            No contacts found yet.
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
