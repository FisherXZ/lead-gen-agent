import { NextRequest, NextResponse } from "next/server";
import { createServiceClient } from "@/lib/supabase/service";
import { withAdminParams } from "@/lib/auth-guard";

/**
 * PATCH /api/team/[userId] — Change a user's role.
 * Admin only. Cannot demote the last admin.
 */
export const PATCH = withAdminParams<{ userId: string }>(
  async (request: NextRequest, adminUser, { userId }) => {
    const body = await request.json();
    const newRole = body.role;

    if (!["admin", "member"].includes(newRole)) {
      return NextResponse.json({ error: "Invalid role" }, { status: 400 });
    }

    const service = createServiceClient();

    // Prevent demoting yourself if you're the last admin
    if (newRole === "member" && userId === adminUser.id) {
      const { data: admins } = await service
        .from("user_roles")
        .select("user_id")
        .eq("role", "admin");

      if ((admins || []).length <= 1) {
        return NextResponse.json(
          { error: "Cannot demote the last admin" },
          { status: 400 }
        );
      }
    }

    const { data, error } = await service
      .from("user_roles")
      .update({ role: newRole, updated_at: new Date().toISOString() })
      .eq("user_id", userId)
      .select();

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    if (!data || data.length === 0) {
      return NextResponse.json({ error: "User role not found" }, { status: 404 });
    }

    return NextResponse.json({ ok: true, userId, role: newRole });
  }
);

/**
 * DELETE /api/team/[userId] — Remove a user from the team.
 * Admin only. Removes from allowlist and deletes auth account.
 * Cannot remove yourself.
 */
export const DELETE = withAdminParams<{ userId: string }>(
  async (_request: NextRequest, adminUser, { userId }) => {
    if (userId === adminUser.id) {
      return NextResponse.json(
        { error: "Cannot remove yourself" },
        { status: 400 }
      );
    }

    const service = createServiceClient();

    // Get user's email to remove from allowlist
    const {
      data: { user: targetUser },
    } = await service.auth.admin.getUserById(userId);

    if (!targetUser) {
      return NextResponse.json({ error: "User not found" }, { status: 404 });
    }

    // Remove from allowlist
    if (targetUser.email) {
      const { error: allowlistError } = await service
        .from("allowed_emails")
        .delete()
        .eq("email", targetUser.email.toLowerCase());
      if (allowlistError) {
        return NextResponse.json({ error: `Failed to remove from allowlist: ${allowlistError.message}` }, { status: 500 });
      }
    }

    // Remove role row (will cascade on user delete, but be explicit)
    const { error: roleError } = await service.from("user_roles").delete().eq("user_id", userId);
    if (roleError) {
      return NextResponse.json({ error: `Failed to remove role: ${roleError.message}` }, { status: 500 });
    }

    // Delete auth user
    const { error } = await service.auth.admin.deleteUser(userId);

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    return NextResponse.json({ ok: true });
  }
);
