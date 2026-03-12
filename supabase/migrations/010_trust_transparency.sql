-- Phase 2: Trust & Transparency
-- Adds rejection_reason, source_count, negative_evidence, and pending index

ALTER TABLE epc_discoveries ADD COLUMN IF NOT EXISTS rejection_reason TEXT;
ALTER TABLE epc_discoveries ADD COLUMN IF NOT EXISTS source_count INTEGER DEFAULT 0;
ALTER TABLE research_attempts ADD COLUMN IF NOT EXISTS negative_evidence JSONB DEFAULT '[]';
ALTER TABLE research_attempts DROP CONSTRAINT IF EXISTS research_attempts_outcome_check;
ALTER TABLE research_attempts ADD CONSTRAINT research_attempts_outcome_check
    CHECK (outcome IN ('found', 'not_found', 'inconclusive', 'rejected_by_reviewer'));
CREATE INDEX IF NOT EXISTS idx_epc_discoveries_pending
    ON epc_discoveries (review_status, confidence)
    WHERE review_status = 'pending';
