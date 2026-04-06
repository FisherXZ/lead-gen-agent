"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { createBrowserClient } from "@supabase/ssr";
import type { User } from "@supabase/supabase-js";

type UserRole = "admin" | "member" | null;

interface AuthContextValue {
  user: User | null;
  accessToken: string | null;
  userRole: UserRole;
  signOut: () => Promise<void>;
  loading: boolean;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  accessToken: null,
  userRole: null,
  signOut: async () => {},
  loading: true,
});

function extractRole(accessToken: string | null): UserRole {
  if (!accessToken) return null;
  try {
    const segment = accessToken.split(".")[1];
    if (!segment) return null;
    const base64 = segment.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
    const payload = JSON.parse(atob(padded));
    if (payload.user_role === "admin") return "admin";
    if (payload.user_role === "member") return "member";
    return null;
  } catch {
    return null;
  }
}

function getSupabase() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [userRole, setUserRole] = useState<UserRole>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const supabase = getSupabase();

    // Get initial session
    supabase.auth.getSession().then(({ data: { session } }) => {
      const token = session?.access_token ?? null;
      setUser(session?.user ?? null);
      setAccessToken(token);
      setUserRole(extractRole(token));
      setLoading(false);
    });

    // Listen for auth changes
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      const token = session?.access_token ?? null;
      setUser(session?.user ?? null);
      setAccessToken(token);
      setUserRole(extractRole(token));
    });

    return () => subscription.unsubscribe();
  }, []);

  const signOut = useCallback(async () => {
    const supabase = getSupabase();
    await supabase.auth.signOut();
    setUser(null);
    setAccessToken(null);
    setUserRole(null);
    window.location.href = "/login";
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, accessToken, userRole, signOut, loading }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

export function useIsAdmin(): boolean {
  const { userRole } = useAuth();
  return userRole === "admin";
}
