import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

import { observeBrowserAuth } from "./browser-auth-generation";
import { synchronizeBusinessAccount } from "./business-grant";

let cachedClient: SupabaseClient | null | undefined;

export function getSupabaseClient(): SupabaseClient | null {
  if (cachedClient !== undefined) {
    return cachedClient;
  }

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  const isMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH === "true";

  if (!supabaseUrl || !supabaseAnonKey) {
    if (isMockAuth) {
      cachedClient = null;
      return cachedClient;
    }
    throw new Error(
      "Missing Supabase environment variables. Please ensure NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY are set."
    );
  }

  cachedClient = createBrowserClient(supabaseUrl, supabaseAnonKey, {
    auth: {
      // The recovery page explicitly exchanges the one-time PKCE code so it can
      // distinguish valid, expired, and reused recovery links.
      detectSessionInUrl: false,
    },
  });
  cachedClient.auth.onAuthStateChange((_event, session) => {
    const userId = session?.user.id ?? null;
    observeBrowserAuth(userId);
    synchronizeBusinessAccount(userId);
  });
  return cachedClient;
}
