import { browserLogoutGeneration } from "./browser-auth-generation";
import { logoutFromApi } from "./argus-api";
import { getSupabaseClient } from "./supabase-client";

let pending: Promise<"verified" | "failed"> | null = null;

/** Consume the provider redirect before the landing page reads any existing account. */
export function completeAuthVerification(): Promise<"none" | "verified" | "failed"> {
  if (pending) return pending;
  const url = new URL(window.location.href);
  const fragment = new URLSearchParams(url.hash.slice(1));
  if (!fragment.has("access_token") && !fragment.has("error")) return Promise.resolve("none");
  const accessToken = fragment.get("access_token");
  const refreshToken = fragment.get("refresh_token");
  url.hash = "";
  window.history.replaceState(null, "", `${url.pathname}${url.search}`);
  pending = (async () => {
    try {
      const logout = logoutFromApi();
      const generation = browserLogoutGeneration();
      const result = await logout;
      if (generation !== browserLogoutGeneration()) return "failed";
      if (result.revocation !== "complete" || result.cookieSync !== "cleared") return "failed";
      const client = getSupabaseClient();
      if (!client) return "failed";
      const response = accessToken && refreshToken && fragment.get("type") === "signup"
        ? await client.auth.setSession({ access_token: accessToken, refresh_token: refreshToken })
        : null;
      if (generation !== browserLogoutGeneration() || !response || response.error || !response.data.user) return "failed";
      return "verified";
    } catch { return "failed"; }
  })();
  void pending.finally(() => { pending = null; });
  return pending;
}
