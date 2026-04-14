-- Add triage-related columns to projects table
-- These support the triage pre-check that classifies projects before research

ALTER TABLE projects ADD COLUMN IF NOT EXISTS name_type TEXT;
-- Values: 'marketing' | 'poi' | 'description' | null
-- Set by scraper on ingest; null for historical rows

ALTER TABLE projects ADD COLUMN IF NOT EXISTS interconnecting_utility TEXT;
-- The grid utility at the point of interconnection
-- Set by CAISO scraper (MISO/PJM put utility in developer field)

ALTER TABLE projects ADD COLUMN IF NOT EXISTS triage_result JSONB;
-- Cached TriageResult from triage_project(). Includes triaged_at timestamp.
-- Reused if < 30 days old. Re-triaged after expiry.
