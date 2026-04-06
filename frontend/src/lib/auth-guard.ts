import { NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";
import { createServiceClient } from "@/lib/supabase/service";
import type { User } from "@supabase/supabase-js";

/** Create a Supabase client scoped to the request's cookies (respects RLS). */
export function createRequestClient(request: NextRequest) {
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll() {},
      },
    }
  );
}

/** Extract the authenticated Supabase user from cookies. */
export async function getAuthUser(request: NextRequest): Promise<User | null> {
  const supabase = createRequestClient(request);
  const {
    data: { user },
  } = await supabase.auth.getUser();
  return user;
}

type AuthHandler = (
  request: NextRequest,
  user: User
) => Promise<NextResponse>;

type AuthHandlerWithParams<P> = (
  request: NextRequest,
  user: User,
  params: P
) => Promise<NextResponse>;

/** Verify user is authenticated, return User or 401 response. */
async function verifyAuth(
  request: NextRequest
): Promise<User | NextResponse> {
  const user = await getAuthUser(request);
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  return user;
}

/** Verify user is admin, return User or 401/403 response. */
async function verifyAdmin(
  request: NextRequest
): Promise<User | NextResponse> {
  const result = await verifyAuth(request);
  if (result instanceof NextResponse) return result;

  const service = createServiceClient();
  const { data } = await service
    .from("user_roles")
    .select("role")
    .eq("user_id", result.id)
    .single();

  if (data?.role !== "admin") {
    return NextResponse.json(
      { error: "Admin access required" },
      { status: 403 }
    );
  }

  return result;
}

/**
 * Wrap an API route handler to require authentication.
 * The handler receives the authenticated User.
 */
export function withAuth(handler: AuthHandler) {
  return async (request: NextRequest) => {
    const result = await verifyAuth(request);
    if (result instanceof NextResponse) return result;
    return handler(request, result);
  };
}

/**
 * Wrap an API route handler to require admin role.
 */
export function withAdmin(handler: AuthHandler) {
  return async (request: NextRequest) => {
    const result = await verifyAdmin(request);
    if (result instanceof NextResponse) return result;
    return handler(request, result);
  };
}

/**
 * Like withAdmin but for route handlers that receive params (dynamic routes).
 */
export function withAdminParams<P>(handler: AuthHandlerWithParams<P>) {
  return async (
    request: NextRequest,
    context: { params: Promise<P> }
  ) => {
    const result = await verifyAdmin(request);
    if (result instanceof NextResponse) return result;
    const params = await context.params;
    return handler(request, result, params);
  };
}
