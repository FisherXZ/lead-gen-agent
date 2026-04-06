import { EpcDiscovery, ConstructionStatus } from "./types";

export type BriefingEventType =
  | "new_lead"
  | "review"
  | "new_project"
  | "status_change"
  | "digest";

export interface BriefingContact {
  id: string;
  full_name: string;
  title: string | null;
  linkedin_url: string | null;
  outreach_context: string | null;
}

export interface BriefingEvent {
  id: string;
  type: BriefingEventType;
  priority: number;
  created_at: string;
  dismissed: boolean;
}

export interface NewLeadEvent extends BriefingEvent {
  type: "new_lead";
  priority: 1;
  project_id: string;
  project_name: string;
  developer: string | null;
  mw_capacity: number | null;
  iso_region: string;
  state: string | null;
  lead_score: number;
  epc_contractor: string;
  confidence: EpcDiscovery["confidence"];
  discovery_id: string;
  entity_id: string | null;
  contacts: BriefingContact[];
  outreach_context: string;
}

export interface ReviewEvent extends BriefingEvent {
  type: "review";
  priority: 2;
  project_id: string;
  project_name: string;
  mw_capacity: number | null;
  iso_region: string;
  epc_contractor: string;
  confidence: EpcDiscovery["confidence"];
  discovery_id: string;
  reasoning_summary: string;
  source_url: string | null;
}

export interface NewProjectEvent extends BriefingEvent {
  type: "new_project";
  priority: 3;
  project_id: string;
  project_name: string;
  developer: string | null;
  mw_capacity: number | null;
  iso_region: string;
  state: string | null;
  status: string | null;
}

export interface StatusChangeEvent extends BriefingEvent {
  type: "status_change";
  priority: 4;
  project_id: string;
  project_name: string;
  previous_status: ConstructionStatus;
  new_status: ConstructionStatus;
  expected_cod: string | null;
}

export interface DigestEvent extends BriefingEvent {
  type: "digest";
  priority: 5;
  period_start: string;
  period_end: string;
  new_projects_count: number;
  epcs_discovered_count: number;
  contacts_found_count: number;
  top_leads: Array<{
    project_name: string;
    epc_contractor: string;
    lead_score: number;
  }>;
}

export type AnyBriefingEvent =
  | NewLeadEvent
  | ReviewEvent
  | NewProjectEvent
  | StatusChangeEvent
  | DigestEvent;

export type BriefingTimeFilter = "today" | "this_week" | "this_month";
export type BriefingRegionFilter = "all" | "ERCOT" | "CAISO" | "MISO";

export interface BriefingFilters {
  region: BriefingRegionFilter;
  timeRange: BriefingTimeFilter;
}

export interface BriefingStats {
  new_leads_this_week: number;
  awaiting_review: number;
  total_epcs_discovered: number;
}
