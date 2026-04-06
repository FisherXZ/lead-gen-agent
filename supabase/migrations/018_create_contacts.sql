-- Helper function for auto-updating updated_at (idempotent)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Contact discovery: store leadership contacts found at EPC companies.
-- Contacts are entity-scoped (not project-scoped) — a contact at McCarthy
-- is relevant across all McCarthy projects.

CREATE TABLE contacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  full_name TEXT NOT NULL,
  title TEXT,
  linkedin_url TEXT,
  source_url TEXT,
  source_method TEXT,  -- 'web_search', 'sec_filing', 'epc_website'
  outreach_context TEXT,
  discovered_at TIMESTAMPTZ DEFAULT now(),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Dedup: one contact per name per entity (case-insensitive)
CREATE UNIQUE INDEX idx_contacts_entity_name ON contacts (entity_id, lower(full_name));
CREATE INDEX idx_contacts_entity_id ON contacts (entity_id);

-- RLS: public read, service-role write (matches entities pattern)
ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read contacts" ON contacts FOR SELECT USING (true);
CREATE POLICY "Service write contacts" ON contacts FOR ALL USING (auth.role() = 'service_role');

-- Auto-update updated_at
CREATE TRIGGER set_contacts_updated_at
  BEFORE UPDATE ON contacts
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Track contact discovery status on entities (fire-and-forget visibility)
-- Status values: NULL (never run), 'pending', 'completed', 'failed'
ALTER TABLE entities
  ADD COLUMN IF NOT EXISTS contact_discovery_status TEXT DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS contact_discovery_error TEXT DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS contacts_discovered_at TIMESTAMPTZ DEFAULT NULL;
