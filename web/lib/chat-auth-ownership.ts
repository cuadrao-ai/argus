import { synchronizeBusinessAccount } from "./business-grant";
import { browserAuthGeneration, requireBrowserAuthGeneration } from "./browser-auth-generation";
import { getSupabaseClient } from "./supabase-client";

export class ChatAccountChangedError extends Error {
  constructor() { super("Chat account changed"); this.name = "ChatAccountChangedError"; }
}

export function requireChatIdentity(
  session: { user: { id: string }; access_token: string } | null,
  expectedUserId: string,
): string {
  if (!session || session.user.id !== expectedUserId) throw new ChatAccountChangedError();
  return session.access_token;
}

export async function authenticatedRequestHeaders(expectedUserId?: string): Promise<Record<string, string>> {
  if (process.env.NEXT_PUBLIC_MOCK_AUTH === "true") return {};
  const client = getSupabaseClient();
  if (!client) throw new Error("Supabase auth client is unavailable in non-mock mode.");
  const generation = browserAuthGeneration();
  const { data, error } = await client.auth.getSession();
  requireBrowserAuthGeneration(generation);
  if (error) throw error;
  const session = data.session;
  synchronizeBusinessAccount(session?.user.id ?? null);
  if (expectedUserId !== undefined) return { Authorization: `Bearer ${requireChatIdentity(session, expectedUserId)}` };
  return session ? { Authorization: `Bearer ${session.access_token}` } : {};
}
