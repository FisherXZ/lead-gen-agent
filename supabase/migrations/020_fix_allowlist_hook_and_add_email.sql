-- Fix: auth hook returned '{}' on success, but Supabase requires {"decision":"continue"}
-- This caused ALL new users to be rejected, even allowlisted ones.

-- Fix the hook function
CREATE OR REPLACE FUNCTION public.check_email_allowlist(event jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    user_email TEXT;
BEGIN
    user_email := lower(event->'user'->>'email');

    IF NOT EXISTS (
        SELECT 1 FROM public.allowed_emails WHERE lower(email) = user_email
    ) THEN
        RETURN jsonb_build_object(
            'error', jsonb_build_object(
                'http_code', 403,
                'message', 'This email is not authorized to access this application.'
            )
        );
    END IF;

    -- Must return {"decision":"continue"} to allow user creation
    RETURN jsonb_build_object('decision', 'continue');
END;
$$;

-- Re-grant permissions (safe to re-run)
GRANT EXECUTE ON FUNCTION public.check_email_allowlist TO supabase_auth_admin;
REVOKE EXECUTE ON FUNCTION public.check_email_allowlist FROM authenticated, anon, public;

-- Add additional emails to allowlist
INSERT INTO allowed_emails (email) VALUES ('fisherxz@berkeley.edu') ON CONFLICT DO NOTHING;
INSERT INTO allowed_emails (email) VALUES ('fisher@thehog.ai') ON CONFLICT DO NOTHING;
