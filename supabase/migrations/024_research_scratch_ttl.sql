-- TTL cleanup for research_scratch table.
-- Deletes entries older than 30 days to prevent unbounded table growth.
-- Run via Supabase pg_cron or manually.

-- Enable pg_cron if not already enabled (Supabase has this available)
-- CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Create cleanup function
CREATE OR REPLACE FUNCTION cleanup_research_scratch()
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM research_scratch
    WHERE created_at < now() - INTERVAL '30 days';
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;

-- Schedule daily cleanup at 3am UTC (uncomment after enabling pg_cron)
-- SELECT cron.schedule('cleanup-research-scratch', '0 3 * * *', 'SELECT cleanup_research_scratch()');
