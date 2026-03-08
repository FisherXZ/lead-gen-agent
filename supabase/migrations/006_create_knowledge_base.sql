-- Knowledge Base: entities, engagements, and research tracking
-- Enables the agent to compound knowledge across research runs

-- ============================================================
-- 1. ENTITIES — directory of companies (developers + EPCs)
-- ============================================================
CREATE TABLE IF NOT EXISTS entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    entity_type TEXT[] NOT NULL DEFAULT '{}',    -- ['developer'], ['epc'], or both
    aliases TEXT[] DEFAULT '{}',
    profile TEXT,                                -- markdown document the agent reads
    profile_rebuilt_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Case-insensitive unique name
CREATE UNIQUE INDEX idx_entities_name_lower ON entities (lower(name));

-- Lookup by type (GIN for array containment: WHERE 'epc' = ANY(entity_type))
CREATE INDEX idx_entities_type ON entities USING GIN (entity_type);

-- Auto-update updated_at (reuses function from 001)
CREATE TRIGGER entities_updated_at
    BEFORE UPDATE ON entities
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- 2. EPC_ENGAGEMENTS — "Developer X hired EPC Y for Project Z"
-- ============================================================
CREATE TABLE IF NOT EXISTS epc_engagements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    developer_entity_id UUID NOT NULL REFERENCES entities(id),
    epc_entity_id UUID NOT NULL REFERENCES entities(id),
    project_id UUID REFERENCES projects(id),
    confidence TEXT NOT NULL CHECK (confidence IN ('confirmed', 'likely', 'possible')),
    sources JSONB NOT NULL DEFAULT '[]',
    state TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Prevent duplicate engagements for same developer+epc+project
CREATE UNIQUE INDEX idx_engagements_dedup
    ON epc_engagements (developer_entity_id, epc_entity_id, project_id)
    WHERE project_id IS NOT NULL;

-- Lookups: by developer, by EPC, by project, by state
CREATE INDEX idx_engagements_developer ON epc_engagements (developer_entity_id);
CREATE INDEX idx_engagements_epc ON epc_engagements (epc_entity_id);
CREATE INDEX idx_engagements_project ON epc_engagements (project_id);
CREATE INDEX idx_engagements_state ON epc_engagements (state);

CREATE TRIGGER epc_engagements_updated_at
    BEFORE UPDATE ON epc_engagements
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- 3. RESEARCH_ATTEMPTS — every research run, success or failure
-- ============================================================
CREATE TABLE IF NOT EXISTS research_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    developer_entity_id UUID REFERENCES entities(id),
    outcome TEXT NOT NULL CHECK (outcome IN ('found', 'not_found', 'inconclusive')),
    epc_found TEXT,
    confidence TEXT,
    searches_performed TEXT[] DEFAULT '{}',
    reasoning TEXT,
    related_findings JSONB DEFAULT '[]',
    tokens_used INTEGER DEFAULT 0,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Lookup by project (to see prior research)
CREATE INDEX idx_research_attempts_project ON research_attempts (project_id);

-- Lookup by developer (to see all research for a developer's projects)
CREATE INDEX idx_research_attempts_developer ON research_attempts (developer_entity_id);

-- ============================================================
-- 4. ROW LEVEL SECURITY — public read, service-role write
-- ============================================================
ALTER TABLE entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE epc_engagements ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_attempts ENABLE ROW LEVEL SECURITY;

-- Entities
CREATE POLICY "Public read entities" ON entities
    FOR SELECT USING (true);
CREATE POLICY "Service role write entities" ON entities
    FOR ALL USING (auth.role() = 'service_role');

-- Engagements
CREATE POLICY "Public read epc_engagements" ON epc_engagements
    FOR SELECT USING (true);
CREATE POLICY "Service role write epc_engagements" ON epc_engagements
    FOR ALL USING (auth.role() = 'service_role');

-- Research Attempts
CREATE POLICY "Public read research_attempts" ON research_attempts
    FOR SELECT USING (true);
CREATE POLICY "Service role write research_attempts" ON research_attempts
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================
-- 5. SEED — harvest existing epc_discoveries into entities + engagements
-- ============================================================

-- Create entity for every distinct developer found in projects
INSERT INTO entities (name, entity_type)
SELECT DISTINCT developer, ARRAY['developer']
FROM projects
WHERE developer IS NOT NULL AND developer != ''
ON CONFLICT ((lower(name))) DO NOTHING;

-- Create entity for every distinct EPC found in accepted discoveries
INSERT INTO entities (name, entity_type)
SELECT DISTINCT epc_contractor, ARRAY['epc']
FROM epc_discoveries
WHERE review_status = 'accepted'
  AND epc_contractor IS NOT NULL
  AND epc_contractor != ''
  AND epc_contractor != 'Unknown'
ON CONFLICT ((lower(name))) DO NOTHING;

-- Create engagements from accepted discoveries
INSERT INTO epc_engagements (developer_entity_id, epc_entity_id, project_id, confidence, sources, state)
SELECT
    dev.id AS developer_entity_id,
    epc.id AS epc_entity_id,
    d.project_id,
    d.confidence,
    d.sources,
    p.state
FROM epc_discoveries d
JOIN projects p ON p.id = d.project_id
JOIN entities dev ON lower(dev.name) = lower(p.developer)
JOIN entities epc ON lower(epc.name) = lower(d.epc_contractor)
WHERE d.review_status = 'accepted'
  AND d.epc_contractor IS NOT NULL
  AND d.epc_contractor != 'Unknown'
ON CONFLICT DO NOTHING;

-- Seed research_attempts from ALL existing discoveries (including not-found)
INSERT INTO research_attempts (project_id, developer_entity_id, outcome, epc_found, confidence, reasoning, related_findings, tokens_used)
SELECT
    d.project_id,
    dev.id AS developer_entity_id,
    CASE
        WHEN d.confidence = 'unknown' THEN 'not_found'
        WHEN d.confidence = 'possible' THEN 'inconclusive'
        ELSE 'found'
    END AS outcome,
    CASE WHEN d.epc_contractor != 'Unknown' THEN d.epc_contractor ELSE NULL END,
    d.confidence,
    d.reasoning,
    d.related_leads,
    d.tokens_used
FROM epc_discoveries d
JOIN projects p ON p.id = d.project_id
LEFT JOIN entities dev ON lower(dev.name) = lower(p.developer)
ORDER BY d.created_at;
