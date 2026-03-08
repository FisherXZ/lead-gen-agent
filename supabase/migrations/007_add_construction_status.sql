-- Add construction lifecycle status (separate from ISO queue status)
ALTER TABLE projects
  ADD COLUMN IF NOT EXISTS construction_status TEXT DEFAULT 'unknown';

-- Constrain to known values
ALTER TABLE projects
  ADD CONSTRAINT construction_status_check
  CHECK (construction_status IN ('unknown', 'pre_construction', 'under_construction', 'completed', 'cancelled'));

-- Index for filtering
CREATE INDEX IF NOT EXISTS idx_projects_construction_status
  ON projects (construction_status);
