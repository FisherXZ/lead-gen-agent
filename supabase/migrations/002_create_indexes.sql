-- Performance indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_projects_iso_region ON projects (iso_region);
CREATE INDEX IF NOT EXISTS idx_projects_fuel_type ON projects (fuel_type);
CREATE INDEX IF NOT EXISTS idx_projects_state ON projects (state);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects (status);
CREATE INDEX IF NOT EXISTS idx_projects_mw_capacity ON projects (mw_capacity);
CREATE INDEX IF NOT EXISTS idx_projects_lead_score ON projects (lead_score DESC);
CREATE INDEX IF NOT EXISTS idx_projects_queue_date ON projects (queue_date DESC);

CREATE INDEX IF NOT EXISTS idx_scrape_runs_iso_region ON scrape_runs (iso_region);
CREATE INDEX IF NOT EXISTS idx_scrape_runs_started_at ON scrape_runs (started_at DESC);
