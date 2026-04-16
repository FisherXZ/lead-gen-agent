-- Fix save_contact upsert: PostgREST cannot reference expression indexes in
-- the `on_conflict` query parameter, so replace the expression-based unique
-- index on (entity_id, lower(full_name)) with a stored generated column +
-- a plain column-based unique index.
--
-- Backfill is automatic: GENERATED ALWAYS AS ... STORED populates existing
-- rows at ADD COLUMN time. The replacement index preserves the same
-- uniqueness semantics (case-insensitive dedup per entity), so no existing
-- rows can newly collide.
--
-- Every statement is idempotent so this migration is safe to re-run after
-- a partial application (e.g. if a prior run left the column in place but
-- never got to CREATE INDEX).
--
-- Verify manually after running:
--   SELECT column_name, is_generated, generation_expression
--     FROM information_schema.columns
--    WHERE table_name = 'contacts' AND column_name = 'full_name_lower';
--   Expected: is_generated='ALWAYS', generation_expression='lower(full_name)'

DROP INDEX IF EXISTS idx_contacts_entity_name;

ALTER TABLE contacts
  ADD COLUMN IF NOT EXISTS full_name_lower TEXT
  GENERATED ALWAYS AS (lower(full_name)) STORED;

CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_entity_name_lower
  ON contacts (entity_id, full_name_lower);
