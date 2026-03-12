CREATE TABLE IF NOT EXISTS agent_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('project', 'global')),
    memory_key TEXT,
    importance INTEGER NOT NULL DEFAULT 5 CHECK (importance BETWEEN 1 AND 10),
    conversation_id UUID,
    project_id UUID REFERENCES projects(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_agent_memory_scope ON agent_memory (scope);
CREATE INDEX idx_agent_memory_key ON agent_memory (memory_key) WHERE memory_key IS NOT NULL;
CREATE INDEX idx_agent_memory_project ON agent_memory (project_id) WHERE project_id IS NOT NULL;
CREATE INDEX idx_agent_memory_importance ON agent_memory (importance DESC);

-- Full-text search
ALTER TABLE agent_memory ADD COLUMN memory_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', memory)) STORED;
CREATE INDEX idx_agent_memory_fts ON agent_memory USING GIN (memory_tsv);

-- Unique index for upsert by memory_key + scope
CREATE UNIQUE INDEX idx_agent_memory_key_scope ON agent_memory (memory_key, scope)
    WHERE memory_key IS NOT NULL;

ALTER TABLE agent_memory ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read agent_memory" ON agent_memory FOR SELECT USING (true);
CREATE POLICY "Service role write agent_memory" ON agent_memory FOR ALL USING (auth.role() = 'service_role');

CREATE TRIGGER agent_memory_updated_at
    BEFORE UPDATE ON agent_memory
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
