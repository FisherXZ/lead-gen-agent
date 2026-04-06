import { NextResponse } from "next/server";
import { createServiceClient } from "@/lib/supabase/service";
import { withAuth } from "@/lib/auth-guard";

export interface TeamMember {
  id: string;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
  role: "admin" | "member";
  last_sign_in_at: string | null;
  created_at: string;
}

export interface PendingInvite {
  email: string;
  created_at: string;
}

/**
 * GET /api/team — List all team members + pending invites.
 * Any authenticated user can view (read-only for members).
 */
export const GET = withAuth(async () => {
  const service = createServiceClient();

  // Fetch all auth users
  const {
    data: { users },
    error: usersError,
  } = await service.auth.admin.listUsers({ perPage: 200 });

  if (usersError) {
    return NextResponse.json(
      { error: usersError.message },
      { status: 500 }
    );
  }

  // Fetch all roles
  const { data: roles } = await service
    .from("user_roles")
    .select("user_id, role");

  const roleMap = new Map(
    (roles || []).map((r: { user_id: string; role: string }) => [
      r.user_id,
      r.role,
    ])
  );

  // Build members list
  const members: TeamMember[] = (users || []).map((u) => ({
    id: u.id,
    email: u.email || "",
    full_name: u.user_metadata?.full_name || u.user_metadata?.name || null,
    avatar_url: u.user_metadata?.avatar_url || u.user_metadata?.picture || null,
    role: (roleMap.get(u.id) as "admin" | "member") || "member",
    last_sign_in_at: u.last_sign_in_at || null,
    created_at: u.created_at,
  }));

  // Find pending invites: emails in allowlist with no matching auth user
  const { data: allowedEmails } = await service
    .from("allowed_emails")
    .select("email, created_at");

  const activeEmails = new Set(
    members.map((m) => m.email.toLowerCase())
  );

  const pendingInvites: PendingInvite[] = (allowedEmails || [])
    .filter(
      (ae: { email: string }) => !activeEmails.has(ae.email.toLowerCase())
    )
    .map((ae: { email: string; created_at: string }) => ({
      email: ae.email,
      created_at: ae.created_at,
    }));

  return NextResponse.json({ members, pendingInvites });
});
