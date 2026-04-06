-- HubSpot CRM integration: settings + sync log.

-- Single-row config table for HubSpot Private App token (encrypted)
CREATE TABLE hubspot_settings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  api_key_encrypted TEXT NOT NULL,
  pipeline_id TEXT,
  deal_stage_id TEXT,
  portal_id TEXT,
  enabled BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Service-role only — encrypted key never exposed to anon
ALTER TABLE hubspot_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service only hubspot_settings" ON hubspot_settings
  FOR ALL USING (auth.role() = 'service_role');

CREATE TRIGGER set_hubspot_settings_updated_at
  BEFORE UPDATE ON hubspot_settings
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Sync history: what was pushed to HubSpot
CREATE TABLE hubspot_sync_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES projects(id),
  entity_id UUID REFERENCES entities(id),
  contact_id UUID REFERENCES contacts(id),
  hubspot_object_type TEXT NOT NULL,  -- 'company', 'deal', 'contact'
  hubspot_object_id TEXT,
  sync_status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'success', 'error'
  error_message TEXT,
  synced_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_sync_log_project ON hubspot_sync_log (project_id, synced_at DESC);
CREATE INDEX idx_sync_log_entity ON hubspot_sync_log (entity_id);

ALTER TABLE hubspot_sync_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read hubspot_sync_log" ON hubspot_sync_log FOR SELECT USING (true);
CREATE POLICY "Service write hubspot_sync_log" ON hubspot_sync_log
  FOR ALL USING (auth.role() = 'service_role');
