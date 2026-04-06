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

    // Prevent demoting the last admin (covers any admin, not just self)
    if (newRole === "member") {
      const { data: targetRole } = await service
        .from("user_roles")
        .select("role")
        .eq("user_id", userId)
        .single();

      if (targetRole?.role === "admin") {
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

    // Post-update safety: verify at least one admin remains
    if (newRole === "member") {
      const { data: remaining } = await service
        .from("user_roles")
        .select("user_id")
        .eq("role", "admin");

      if (!remaining || remaining.length === 0) {
        // Revert — restore admin role
        await service
          .from("user_roles")
          .update({ role: "admin", updated_at: new Date().toISOString() })
          .eq("user_id", userId);
        return NextResponse.json(
          { error: "Cannot demote the last admin" },
          { status: 409 }
        );
      }
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

    // Prevent deleting the last admin
    const { data: targetRole } = await service
      .from("user_roles")
      .select("role")
      .eq("user_id", userId)
      .single();

    if (targetRole?.role === "admin") {
      const { data: admins } = await service
        .from("user_roles")
        .select("user_id")
        .eq("role", "admin");

      if ((admins || []).length <= 1) {
        return NextResponse.json(
          { error: "Cannot remove the last admin" },
          { status: 400 }
        );
      }
    }

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
