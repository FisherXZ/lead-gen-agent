import { NextRequest, NextResponse } from "next/server";
import { createServiceClient } from "@/lib/supabase/service";
import { withAdmin } from "@/lib/auth-guard";

/**
 * POST /api/team/invite — Add an email to the allowlist (invite).
 * Admin only. The admin notifies the person manually to sign in with Google.
 */
export const POST = withAdmin(async (request: NextRequest) => {
  const body = await request.json();
  const email = (body.email || "").trim().toLowerCase();

  if (!email || !email.includes("@")) {
    return NextResponse.json({ error: "Invalid email" }, { status: 400 });
  }

  const service = createServiceClient();
  const { error } = await service.from("allowed_emails").insert({ email });

  if (error) {
    if (error.code === "23505") {
      return NextResponse.json(
        { error: "This email is already invited" },
        { status: 409 }
      );
    }
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ ok: true, email });
});
