-- Migration 023: Roles, Preferences, and Custom Access Token Hook
-- Adds admin/member role system, per-user preferences, and JWT role injection.
--
-- MANUAL STEP AFTER RUNNING:
--   Supabase Dashboard > Authentication > Hooks > "Customize Access Token (JWT)"
--   → Enable and point to: public.custom_access_token_hook
--   Then sign out and back in to get the new JWT claims.

-- ============================================================
-- 1. user_roles table
-- ============================================================

CREATE TABLE IF NOT EXISTS user_roles (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin', 'member')),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY;

-- Authenticated users can read their own role
CREATE POLICY "Users can read own role"
    ON user_roles FOR SELECT
    USING (auth.uid() = user_id);

-- Service role has full access (used by admin API routes)
-- (service_role bypasses RLS by default, no policy needed)

-- Seed Fisher as admin
INSERT INTO user_roles (user_id, role)
SELECT id, 'admin'
FROM auth.users
WHERE email = 'fisher262425@gmail.com'
ON CONFLICT (user_id) DO UPDATE SET role = 'admin';

-- Seed Liav as admin
INSERT INTO user_roles (user_id, role)
SELECT id, 'admin'
FROM auth.users
WHERE email = 'liav@civrobotics.com'
ON CONFLICT (user_id) DO UPDATE SET role = 'admin';

-- Backfill any existing users as members
INSERT INTO user_roles (user_id, role)
SELECT id, 'member'
FROM auth.users
WHERE id NOT IN (SELECT user_id FROM user_roles)
ON CONFLICT (user_id) DO NOTHING;

-- ============================================================
-- 2. user_preferences table
-- ============================================================

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own preferences"
    ON user_preferences FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Backfill existing users with empty preferences
INSERT INTO user_preferences (user_id)
SELECT id FROM auth.users
ON CONFLICT (user_id) DO NOTHING;

-- ============================================================
-- 3. Auto-provision trigger for new users
-- ============================================================

CREATE OR REPLACE FUNCTION public.handle_new_user_role_and_prefs()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    assigned_role TEXT := 'member';
BEGIN
    -- Auto-promote known admin emails
    IF NEW.email IN ('fisher262425@gmail.com', 'liav@civrobotics.com') THEN
        assigned_role := 'admin';
    END IF;

    INSERT INTO user_roles (user_id, role) VALUES (NEW.id, assigned_role)
    ON CONFLICT (user_id) DO NOTHING;

    INSERT INTO user_preferences (user_id) VALUES (NEW.id)
    ON CONFLICT (user_id) DO NOTHING;

    RETURN NEW;
END;
$$;

-- Drop if exists to avoid duplicate triggers
DROP TRIGGER IF EXISTS on_auth_user_created_provision ON auth.users;

CREATE TRIGGER on_auth_user_created_provision
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user_role_and_prefs();

-- ============================================================
-- 4. Custom Access Token Hook
--    Injects user_role into JWT claims on every token mint/refresh.
-- ============================================================

CREATE OR REPLACE FUNCTION public.custom_access_token_hook(event jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    claims jsonb;
    user_role text;
BEGIN
    claims := event->'claims';

    SELECT role INTO user_role
    FROM user_roles
    WHERE user_id = (event->>'user_id')::uuid;

    -- Inject role into claims (default to 'member' if no row found)
    claims := jsonb_set(claims, '{user_role}', to_jsonb(COALESCE(user_role, 'member')));

    RETURN jsonb_build_object('claims', claims);
END;
$$;

-- Grant to supabase_auth_admin (required for auth hooks)
GRANT EXECUTE ON FUNCTION public.custom_access_token_hook TO supabase_auth_admin;
REVOKE EXECUTE ON FUNCTION public.custom_access_token_hook FROM authenticated, anon, public;

-- The hook needs to read user_roles
GRANT SELECT ON TABLE public.user_roles TO supabase_auth_admin;

-- ============================================================
-- 5. is_admin() SQL helper for use in RLS policies
-- ============================================================

CREATE OR REPLACE FUNCTION public.is_admin()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT COALESCE((auth.jwt() ->> 'user_role') = 'admin', false);
$$;
