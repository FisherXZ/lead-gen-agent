"use client";

import { DigestEvent } from "@/lib/briefing-types";

interface DigestCardProps {
  event: DigestEvent;
}

export function DigestCard({ event }: DigestCardProps) {
  return (
    <div className="bg-[--surface-overlay] rounded-lg p-5">
      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-sans font-medium uppercase tracking-wider bg-[--surface-overlay] text-[--text-tertiary] mb-3">
        Weekly Digest
      </span>

      <div className="grid grid-cols-3 gap-4 mb-4">
        <div>
          <div className="text-2xl font-serif text-[--text-primary]">
            {event.new_projects_count}
          </div>
          <div className="text-xs font-sans text-[--text-tertiary] uppercase tracking-wider">
            New Projects
          </div>
        </div>
        <div>
          <div className="text-2xl font-serif text-[--text-primary]">
            {event.epcs_discovered_count}
          </div>
          <div className="text-xs font-sans text-[--text-tertiary] uppercase tracking-wider">
            EPCs Discovered
          </div>
        </div>
        <div>
          <div className="text-2xl font-serif text-[--text-primary]">
            {event.contacts_found_count}
          </div>
          <div className="text-xs font-sans text-[--text-tertiary] uppercase tracking-wider">
            Contacts Found
          </div>
        </div>
      </div>

      {event.top_leads.length > 0 && (
        <div className="pt-3 border-t border-[--border-subtle]">
          <div className="text-xs font-sans text-[--text-tertiary] uppercase tracking-wider mb-2">
            Top Leads
          </div>
          <div className="space-y-1.5">
            {event.top_leads.map((lead, i) => (
              <div key={i} className="flex items-center justify-between text-sm">
                <span className="text-[--text-primary]">
                  {lead.epc_contractor}
                  <span className="text-[--text-tertiary]">
                    {" "}&mdash; {lead.project_name}
                  </span>
                </span>
                <span
                  className={`font-mono text-xs ${
                    lead.lead_score >= 70
                      ? "text-[--status-green]"
                      : "text-[--accent-amber]"
                  }`}
                >
                  {lead.lead_score}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
