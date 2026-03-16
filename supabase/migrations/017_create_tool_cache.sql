-- Tool cache table for structured data source tools.
-- Survives Railway process restarts. Tiered TTLs per source.
CREATE TABLE IF NOT EXISTS tool_cache (
    cache_key TEXT PRIMARY KEY,
    tool_name TEXT NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

-- Index for TTL cleanup and tool-level queries
CREATE INDEX idx_tool_cache_expires ON tool_cache (expires_at);
CREATE INDEX idx_tool_cache_tool ON tool_cache (tool_name);

-- RLS: service-role only (tools run server-side)
ALTER TABLE tool_cache ENABLE ROW LEVEL SECURITY;
