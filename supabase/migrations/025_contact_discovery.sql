-- Migration 025: Contact discovery — extend contacts + new junction/scoring tables

-- 1. Extend contacts table with enrichment columns
ALTER TABLE contacts
  ADD COLUMN IF NOT EXISTS email TEXT,
  ADD COLUMN IF NOT EXISTS phone TEXT,
  ADD COLUMN IF NOT EXISTS email_source TEXT,
  ADD COLUMN IF NOT EXISTS phone_source TEXT,
  ADD COLUMN IF NOT EXISTS linkedin_headline TEXT,
  ADD COLUMN IF NOT EXISTS linkedin_location TEXT,
  ADD COLUMN IF NOT EXISTS linkedin_experience JSONB,
  ADD COLUMN IF NOT EXISTS profile_scraped_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS hubspot_contact_id TEXT;

-- 2. project_contacts: links a contact to a specific project
--    Contacts are entity-scoped by default; this table adds project-level relevance.
CREATE TABLE project_contacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
  relevance_note TEXT,
  discovered_via TEXT,  -- 'hubspot_lookup', 'linkedin', 'exa', 'osha', 'epc_website', 'web_search'
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(project_id, contact_id)
);

CREATE INDEX idx_project_contacts_project_id ON project_contacts (project_id);
CREATE INDEX idx_project_contacts_contact_id ON project_contacts (contact_id);

-- RLS: public read, service-role write (matches contacts pattern)
ALTER TABLE project_contacts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read project_contacts" ON project_contacts FOR SELECT USING (true);
CREATE POLICY "Service write project_contacts" ON project_contacts FOR ALL USING (auth.role() = 'service_role');

-- 3. contact_persona_scores: AI + user-override scoring for persona fit
--    Generated columns combine AI scores with optional user overrides.
CREATE TABLE contact_persona_scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,

  -- AI-assigned scores
  ai_role_aligned BOOLEAN,
  ai_is_decision_maker BOOLEAN,
  ai_project_relevant BOOLEAN,
  ai_persona_fit BOOLEAN,
  ai_reasoning JSONB,
  ai_classified_at TIMESTAMPTZ,

  -- User overrides (null = defer to AI)
  user_role_aligned BOOLEAN,
  user_is_decision_maker BOOLEAN,
  user_project_relevant BOOLEAN,
  user_persona_fit BOOLEAN,
  user_override_at TIMESTAMPTZ,

  -- Computed: true only if all four criteria pass (user override wins when set)
  is_match BOOLEAN GENERATED ALWAYS AS (
    COALESCE(user_role_aligned, ai_role_aligned) IS TRUE AND
    COALESCE(user_is_decision_maker, ai_is_decision_maker) IS TRUE AND
    COALESCE(user_project_relevant, ai_project_relevant) IS TRUE AND
    COALESCE(user_persona_fit, ai_persona_fit) IS TRUE
  ) STORED,

  -- Computed: 0.00–1.00 weighted equally across four criteria
  match_score NUMERIC GENERATED ALWAYS AS (
    (CASE WHEN COALESCE(user_role_aligned, ai_role_aligned) THEN 0.25 ELSE 0 END +
     CASE WHEN COALESCE(user_is_decision_maker, ai_is_decision_maker) THEN 0.25 ELSE 0 END +
     CASE WHEN COALESCE(user_project_relevant, ai_project_relevant) THEN 0.25 ELSE 0 END +
     CASE WHEN COALESCE(user_persona_fit, ai_persona_fit) THEN 0.25 ELSE 0 END)
  ) STORED,

  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(contact_id)
);

-- RLS: public read, service-role write (matches contacts pattern)
ALTER TABLE contact_persona_scores ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read contact_persona_scores" ON contact_persona_scores FOR SELECT USING (true);
CREATE POLICY "Service write contact_persona_scores" ON contact_persona_scores FOR ALL USING (auth.role() = 'service_role');

-- Auto-update updated_at (reuses function from migration 018)
CREATE TRIGGER set_contact_persona_scores_updated_at
  BEFORE UPDATE ON contact_persona_scores
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
