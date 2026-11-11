import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

export async function createClient() {
  const cookieStore = await cookies();

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseAnonKey) {
    throw new Error(
      "Missing Supabase environment variables. Please ensure NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY are set in your .env file."
    );
  }

  return createServerClient(
    supabaseUrl,
    supabaseAnonKey,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) => {
              cookieStore.set(name, value, options);
            });
          } catch {}
        },
      },
    }
  );
}

function sessionStorageKey(supabaseUrl: string): string | null {
  try {
    return `sb-${new URL(supabaseUrl).hostname.split(".")[0]}-auth-token`;
  } catch {
    return null;
  }
}

function hasSessionCookie(request: NextRequest, storageKey: string): boolean {
  return request.cookies.getAll().some(
    (cookie) => cookie.name === storageKey || cookie.name.startsWith(`${storageKey}.`),
  );
}

export async function publishRefreshedSession(
  request: NextRequest,
  response: NextResponse,
): Promise<NextResponse> {
  if (process.env.NEXT_PUBLIC_MOCK_AUTH === "true") return response;
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!supabaseUrl || !supabaseAnonKey) return response;
  const storageKey = sessionStorageKey(supabaseUrl);
  if (!storageKey || !hasSessionCookie(request, storageKey)) return response;

  let outgoing = response;
  const supabase = createServerClient(supabaseUrl, supabaseAnonKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(
        cookiesToSet: { name: string; value: string; options: CookieOptions }[],
        headers: Record<string, string>,
      ) {
        cookiesToSet.forEach(({ name, value }) => {
          request.cookies.set(name, value);
        });
        // The render reads the request this response was built from. Rebuild a
        // pass-through after the jar changes so the page does not refresh again.
        if (outgoing.status === 200) {
          outgoing = NextResponse.next({ request });
        }
        cookiesToSet.forEach(({ name, value, options }) => {
          outgoing.cookies.set(name, value, options);
        });
        Object.entries(headers).forEach(([key, value]) => {
          outgoing.headers.set(key, value);
        });
      },
    },
  });
  try {
    await supabase.auth.getUser();
  } catch {
    return outgoing;
  }
  return outgoing;
}
