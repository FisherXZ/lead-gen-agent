export interface Project {
  id: string;
  queue_id: string;
  iso_region: string;
  project_name: string | null;
  developer: string | null;
  epc_company: string | null;
  state: string | null;
  county: string | null;
  latitude: number | null;
  longitude: number | null;
  mw_capacity: number | null;
  fuel_type: string | null;
  queue_date: string | null;
  expected_cod: string | null;
  status: string | null;
  source: string;
  lead_score: number;
  construction_status: ConstructionStatus;
  raw_data: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export type ConstructionStatus =
  | "unknown"
  | "pre_construction"
  | "under_construction"
  | "completed"
  | "cancelled";

export interface ScrapeRun {
  id: string;
  iso_region: string;
  status: string;
  projects_found: number;
  projects_upserted: number;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface Filters {
  iso_region: string;
  state: string;
  status: string;
  fuel_type: string;
  mw_min: number;
  mw_max: number;
  cod_year_min: number;
  cod_year_max: number;
  construction_status: string;
  search: string;
}

export interface EpcSource {
  channel: string;
  publication: string | null;
  date: string | null;
  url: string | null;
  excerpt: string;
  reliability: "high" | "medium" | "low";
}

export interface EpcDiscovery {
  id: string;
  project_id: string;
  epc_contractor: string;
  confidence: "confirmed" | "likely" | "possible" | "unknown";
  sources: EpcSource[];
  reasoning: string | null;
  related_leads: Record<string, unknown>[];
  review_status: "pending" | "accepted" | "rejected";
  agent_log: Record<string, unknown>[];
  tokens_used: number;
  created_at: string;
  updated_at: string;
}

export type EpcFilter = "all" | "needs_research" | "has_epc" | "pending_review";
