-- Backfill construction_status from existing data (v2 — corrected logic)
-- Re-run safe: updates all rows, not just 'unknown'
UPDATE projects SET construction_status = CASE
  WHEN lower(status) LIKE '%withdrawn%' THEN 'cancelled'
  WHEN expected_cod IS NOT NULL AND expected_cod < now()::date THEN 'completed'
  WHEN lower(status) LIKE '%completed%' AND expected_cod >= now()::date THEN 'under_construction'
  WHEN lower(status) LIKE '%active%' AND expected_cod >= now()::date THEN 'pre_construction'
  ELSE 'unknown'
END;
