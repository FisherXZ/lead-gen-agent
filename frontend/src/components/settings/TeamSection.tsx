"use client";

import { useEffect, useState, useCallback } from "react";
import { useAuth, useIsAdmin } from "@/lib/auth";
import type { TeamMember, PendingInvite } from "@/app/api/team/route";

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "Never";
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function Initials({ name, email }: { name: string | null; email: string }) {
  const text = name || email;
  const initials = text
    .split(/[\s@]+/)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase() || "")
    .join("");

  return (
    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-surface-overlay text-xs font-medium text-text-secondary">
      {initials}
    </div>
  );
}

function Avatar({
  url,
  name,
  email,
}: {
  url: string | null;
  name: string | null;
  email: string;
}) {
  if (url) {
    return (
      <img
        src={url}
        alt=""
        className="h-8 w-8 rounded-full object-cover"
        referrerPolicy="no-referrer"
      />
    );
  }
  return <Initials name={name} email={email} />;
}

export default function TeamSection() {
  const { user } = useAuth();
  const isAdmin = useIsAdmin();
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [pendingInvites, setPendingInvites] = useState<PendingInvite[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Invite state
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteStatus, setInviteStatus] = useState<
    "idle" | "sending" | "error"
  >("idle");
  const [inviteError, setInviteError] = useState("");

  // Role change state
  const [changingRole, setChangingRole] = useState<string | null>(null);

  const fetchTeam = useCallback(async () => {
    try {
      const res = await fetch("/api/team");
      if (res.ok) {
        const data = await res.json();
        setMembers(data.members || []);
        setPendingInvites(data.pendingInvites || []);
        setError("");
      } else {
        setError("Failed to load team");
      }
    } catch {
      setError("Could not reach the server.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTeam();
  }, [fetchTeam]);

  async function handleInvite() {
    const email = inviteEmail.trim().toLowerCase();
    if (!email || !email.includes("@")) return;

    setInviteStatus("sending");
    setInviteError("");

    try {
      const res = await fetch("/api/team/invite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      if (res.ok) {
        setInviteEmail("");
        setInviteStatus("idle");
        fetchTeam();
      } else {
        setInviteStatus("error");
        setInviteError(data.error || "Failed to invite");
      }
    } catch {
      setInviteStatus("error");
      setInviteError("Could not reach the server.");
    }
  }

  async function handleRoleChange(userId: string, newRole: string) {
    setChangingRole(userId);
    try {
      const res = await fetch(`/api/team/${userId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: newRole }),
      });
      const data = await res.json();
      if (res.ok) {
        fetchTeam();
      } else {
        setError(data.error || "Failed to change role");
      }
    } catch {
      setError("Could not reach the server.");
    } finally {
      setChangingRole(null);
    }
  }

  async function handleRemoveMember(userId: string) {
    try {
      const res = await fetch(`/api/team/${userId}`, {
        method: "DELETE",
      });
      const data = await res.json();
      if (res.ok) {
        fetchTeam();
      } else {
        setError(data.error || "Failed to remove member");
      }
    } catch {
      setError("Could not reach the server.");
    }
  }

  async function handleCancelInvite(email: string) {
    try {
      const res = await fetch("/api/allowed-emails", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (res.ok) {
        fetchTeam();
      } else {
        const data = await res.json();
        setError(data.error || "Failed to cancel invite");
      }
    } catch {
      setError("Could not reach the server.");
    }
  }

  return (
    <div className="rounded-lg border border-border-subtle bg-surface-raised p-6">
      <h2 className="font-serif text-lg font-medium text-text-primary">
        Team
      </h2>
      <p className="mt-1 text-sm text-text-secondary">
        {isAdmin
          ? "Manage who has access to this workspace."
          : "People with access to this workspace."}
      </p>

      {/* Invite form — admin only */}
      {isAdmin && (
        <div className="mt-4">
          <div className="flex gap-2">
            <input
              type="email"
              value={inviteEmail}
              onChange={(e) => {
                setInviteEmail(e.target.value);
                if (inviteError) setInviteError("");
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleInvite();
              }}
              placeholder="name@company.com"
              className="h-10 flex-1 rounded-md border border-border-default bg-surface-overlay px-3 text-sm text-text-primary placeholder:text-text-tertiary focus:border-border-focus focus:outline-none focus:ring-1 focus:ring-border-focus"
            />
            <button
              onClick={handleInvite}
              disabled={!inviteEmail.trim() || inviteStatus === "sending"}
              className="rounded-md bg-accent-amber px-4 py-2 text-sm font-medium text-surface-primary transition-colors hover:bg-accent-amber/90 disabled:opacity-50"
            >
              {inviteStatus === "sending" ? "Inviting..." : "Invite"}
            </button>
          </div>
          {inviteError && (
            <p className="mt-2 text-sm text-status-red">{inviteError}</p>
          )}
          <p className="mt-2 text-xs text-text-tertiary">
            Add their email, then let them know to sign in with Google.
          </p>
        </div>
      )}

      {/* Error */}
      {error && (
        <p className="mt-4 text-sm text-status-red">{error}</p>
      )}

      {/* Members list */}
      <div className="mt-6">
        <p className="text-xs font-medium uppercase tracking-wider text-text-tertiary">
          Members
        </p>
        <div className="mt-3 space-y-1">
          {loading ? (
            <p className="py-3 text-sm text-text-tertiary">Loading...</p>
          ) : members.length === 0 ? (
            <p className="py-3 text-sm text-text-tertiary">No members yet.</p>
          ) : (
            members.map((member) => {
              const isYou = member.id === user?.id;
              return (
                <div
                  key={member.id}
                  className="flex items-center gap-3 rounded-md px-3 py-2.5 transition-colors hover:bg-surface-overlay/50"
                >
                  <Avatar
                    url={member.avatar_url}
                    name={member.full_name}
                    email={member.email}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium text-text-primary">
                        {member.full_name || member.email}
                      </span>
                      {isYou && (
                        <span className="text-xs text-text-tertiary">you</span>
                      )}
                    </div>
                    {member.full_name && (
                      <p className="truncate text-xs text-text-tertiary">
                        {member.email}
                      </p>
                    )}
                  </div>

                  {/* Last active */}
                  <span className="hidden text-xs text-text-tertiary sm:block">
                    {formatDate(member.last_sign_in_at)}
                  </span>

                  {/* Role badge / selector */}
                  {isAdmin && !isYou ? (
                    <select
                      value={member.role}
                      onChange={(e) =>
                        handleRoleChange(member.id, e.target.value)
                      }
                      disabled={changingRole === member.id}
                      className="h-7 rounded border border-border-subtle bg-surface-overlay px-2 text-xs text-text-secondary focus:border-border-focus focus:outline-none"
                    >
                      <option value="admin">Admin</option>
                      <option value="member">Member</option>
                    </select>
                  ) : (
                    <span
                      className={`rounded px-2 py-0.5 text-xs font-medium ${
                        member.role === "admin"
                          ? "bg-accent-amber-muted text-accent-amber"
                          : "bg-surface-overlay text-text-tertiary"
                      }`}
                    >
                      {member.role === "admin" ? "Admin" : "Member"}
                    </span>
                  )}

                  {/* Remove button — admin only, not self */}
                  {isAdmin && !isYou ? (
                    <button
                      onClick={() => handleRemoveMember(member.id)}
                      className="text-text-tertiary transition-colors hover:text-status-red"
                      title="Remove from team"
                    >
                      <svg
                        className="h-4 w-4"
                        fill="none"
                        viewBox="0 0 24 24"
                        strokeWidth={1.5}
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M6 18L18 6M6 6l12 12"
                        />
                      </svg>
                    </button>
                  ) : (
                    <div className="w-4" />
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Pending invites */}
      {pendingInvites.length > 0 && (
        <div className="mt-6">
          <p className="text-xs font-medium uppercase tracking-wider text-text-tertiary">
            Pending Invites
          </p>
          <div className="mt-3 space-y-1">
            {pendingInvites.map((invite) => (
              <div
                key={invite.email}
                className="flex items-center gap-3 rounded-md px-3 py-2.5"
              >
                <div className="flex h-8 w-8 items-center justify-center rounded-full border border-dashed border-border-default">
                  <span className="inline-block h-2 w-2 rounded-full bg-status-amber" />
                </div>
                <div className="min-w-0 flex-1">
                  <span className="text-sm text-text-secondary">
                    {invite.email}
                  </span>
                </div>
                <span className="text-xs text-text-tertiary">
                  Invited {formatDate(invite.created_at)}
                </span>
                {isAdmin && (
                  <button
                    onClick={() => handleCancelInvite(invite.email)}
                    className="text-text-tertiary transition-colors hover:text-status-red"
                    title="Cancel invite"
                  >
                    <svg
                      className="h-4 w-4"
                      fill="none"
                      viewBox="0 0 24 24"
                      strokeWidth={1.5}
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M6 18L18 6M6 6l12 12"
                      />
                    </svg>
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
