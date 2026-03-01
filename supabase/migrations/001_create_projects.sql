-- Projects table: stores filtered solar projects from ISO interconnection queues
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    queue_id TEXT NOT NULL,
    iso_region TEXT NOT NULL,
    project_name TEXT,
    developer TEXT,
    epc_company TEXT,
    state TEXT,
    county TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    mw_capacity DOUBLE PRECISION,
    fuel_type TEXT,
    queue_date DATE,
    expected_cod DATE,
    status TEXT,
    source TEXT DEFAULT 'iso_queue',
    lead_score INTEGER DEFAULT 0,
    raw_data JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT unique_iso_queue UNIQUE (iso_region, queue_id)
);

-- Scrape runs table: tracks each scraper execution for monitoring
CREATE TABLE IF NOT EXISTS scrape_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    iso_region TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    projects_found INTEGER DEFAULT 0,
    projects_upserted INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ
);

-- Auto-update updated_at on row changes
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();
