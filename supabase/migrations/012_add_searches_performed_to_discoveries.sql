-- Add missing searches_performed column to epc_discoveries.
-- The code (db.store_discovery) has been writing this field since Phase 2,
-- but the column was only created on research_attempts (migration 006),
-- not on epc_discoveries (migration 004). This caused every insert to fail.

ALTER TABLE epc_discoveries ADD COLUMN IF NOT EXISTS searches_performed TEXT[] DEFAULT '{}';

-- Also ensure migration 010 columns exist (source_count, rejection_reason)
-- in case that migration was never applied.
ALTER TABLE epc_discoveries ADD COLUMN IF NOT EXISTS source_count INTEGER DEFAULT 0;
ALTER TABLE epc_discoveries ADD COLUMN IF NOT EXISTS rejection_reason TEXT;

-- And migration 010's research_attempts changes
ALTER TABLE research_attempts ADD COLUMN IF NOT EXISTS negative_evidence JSONB DEFAULT '[]';
ALTER TABLE research_attempts DROP CONSTRAINT IF EXISTS research_attempts_outcome_check;
ALTER TABLE research_attempts ADD CONSTRAINT research_attempts_outcome_check
    CHECK (outcome IN ('found', 'not_found', 'inconclusive', 'rejected_by_reviewer'));

-- And migration 011's agent_memory table
CREATE TABLE IF NOT EXISTS agent_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'global' CHECK (scope IN ('project', 'global')),
    memory_key TEXT,
    importance INTEGER DEFAULT 5 CHECK (importance BETWEEN 1 AND 10),
    conversation_id UUID,
    project_id UUID REFERENCES projects(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Pending discoveries index from migration 010
CREATE INDEX IF NOT EXISTS idx_epc_discoveries_pending
    ON epc_discoveries (review_status, confidence)
    WHERE review_status = 'pending';
