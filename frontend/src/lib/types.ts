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
  raw_data: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

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
  search: string;
}
