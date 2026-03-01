-- Row-Level Security: public read, service-role write
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE scrape_runs ENABLE ROW LEVEL SECURITY;

-- Anyone can read projects (dashboard uses anon key)
CREATE POLICY "Public read access" ON projects
    FOR SELECT USING (true);

-- Only service role can insert/update (scrapers)
CREATE POLICY "Service role write access" ON projects
    FOR ALL USING (auth.role() = 'service_role');

-- Anyone can read scrape_runs (for "last updated" display)
CREATE POLICY "Public read scrape_runs" ON scrape_runs
    FOR SELECT USING (true);

CREATE POLICY "Service role write scrape_runs" ON scrape_runs
    FOR ALL USING (auth.role() = 'service_role');
