import { NextRequest, NextResponse } from "next/server";
import { createServiceClient } from "@/lib/supabase/service";
import { withAuth, withAdmin } from "@/lib/auth-guard";

export const GET = withAuth(async () => {
  const service = createServiceClient();
  const { data, error } = await service
    .from("allowed_emails")
    .select("email, created_at")
    .order("created_at", { ascending: true });

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ emails: data });
});

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
        { error: "Email already exists" },
        { status: 409 }
      );
    }
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ ok: true, email });
});

export const DELETE = withAdmin(async (request: NextRequest, user) => {
  const body = await request.json();
  const email = (body.email || "").trim().toLowerCase();

  if (!email) {
    return NextResponse.json({ error: "Email required" }, { status: 400 });
  }

  if (email === user.email?.toLowerCase()) {
    return NextResponse.json(
      { error: "Cannot remove your own email" },
      { status: 400 }
    );
  }

  const service = createServiceClient();
  const { error } = await service
    .from("allowed_emails")
    .delete()
    .eq("email", email);

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ ok: true });
});
