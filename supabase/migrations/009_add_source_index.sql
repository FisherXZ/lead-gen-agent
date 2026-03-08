-- Index on source column for filtering ISO queue vs GEM tracker projects
CREATE INDEX IF NOT EXISTS idx_projects_source ON projects (source);
