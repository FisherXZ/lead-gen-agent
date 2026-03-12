-- Persistent scratchpad for agent research sessions.
-- Intermediate findings (candidates, dead ends, sources) are stored here
-- so they survive context compaction during long research runs.

CREATE TABLE IF NOT EXISTS research_scratch (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX idx_research_scratch_session_key
    ON research_scratch (session_id, key);

ALTER TABLE research_scratch ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON research_scratch FOR SELECT USING (true);
CREATE POLICY "Service write" ON research_scratch FOR ALL USING (auth.role() = 'service_role');
