import { NextRequest, NextResponse } from "next/server";
import { withAuth, createRequestClient } from "@/lib/auth-guard";

/**
 * GET /api/preferences — Return the current user's preferences.
 */
export const GET = withAuth(async (request: NextRequest, user) => {
  const supabase = createRequestClient(request);
  const { data, error } = await supabase
    .from("user_preferences")
    .select("preferences")
    .eq("user_id", user.id)
    .maybeSingle();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ preferences: data?.preferences || {} });
});

/**
 * PATCH /api/preferences — Merge keys into the user's preferences.
 * Body: { "key": "value", ... }
 */
export const PATCH = withAuth(async (request: NextRequest, user) => {
  const updates = await request.json();
  if (
    typeof updates !== "object" ||
    updates === null ||
    Array.isArray(updates)
  ) {
    return NextResponse.json(
      { error: "Body must be a JSON object" },
      { status: 400 }
    );
  }

  const supabase = createRequestClient(request);

  // Get existing preferences
  const { data: existing } = await supabase
    .from("user_preferences")
    .select("preferences")
    .eq("user_id", user.id)
    .maybeSingle();

  const merged = { ...(existing?.preferences || {}), ...updates };

  const { error } = await supabase.from("user_preferences").upsert(
    {
      user_id: user.id,
      preferences: merged,
      updated_at: new Date().toISOString(),
    },
    { onConflict: "user_id" }
  );

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ preferences: merged });
});
