import {
  apiFetch,
  persistBrowserSession,
  unauthenticatedApiFetch,
  type ApiLanguage,
  type AuthResponsePayload,
  type Conversation,
} from "@/lib/argus-api";
import { acquirePasswordAuthCaptchaToken } from "@/lib/guest-captcha";
import type { GuestPendingActionSummary } from "@/lib/guest-conversion";

export async function requestAccess(payload: {
  email: string;
  language: ApiLanguage;
}): Promise<{ accepted: true }> {
  return unauthenticatedApiFetch<{ accepted: true }>(
    "/auth/access-requests",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function createGuestHandoff(payload: {
  handoff_kind?: "existing_account" | "new_account_signup";
  destination_email: string;
  source_conversation_id: string;
  pending_action?: GuestPendingActionSummary | null;
}) {
  return apiFetch<{ handoff_id: string; expires_at: string }>(
    "/auth/guest/handoffs",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function registerGuestAccount(payload: {
  email: string;
  password: string;
  language: ApiLanguage;
  display_name?: string | null;
  username?: string | null;
  source_conversation_id: string;
  pending_action?: GuestPendingActionSummary | null;
  age_confirmed_at: string;
}) {
  if (!payload.age_confirmed_at) {
    throw Object.assign(new Error("age_confirmation_required"), {
      code: "age_confirmation_required",
    });
  }
  await createGuestHandoff({
    handoff_kind: "new_account_signup",
    destination_email: payload.email,
    source_conversation_id: payload.source_conversation_id,
    pending_action: payload.pending_action,
  });
  const captchaToken = await acquirePasswordAuthCaptchaToken();
  const response = await apiFetch<AuthResponsePayload>("/auth/guest/signup", {
    method: "POST",
    body: JSON.stringify({
      age_confirmed_at: payload.age_confirmed_at,
      email: payload.email,
      password: payload.password,
      captcha_token: captchaToken,
      language: payload.language,
      display_name: payload.display_name,
      username: payload.username,
    }),
  });
  await persistBrowserSession(response);
  return { response, needsEmailConfirmation: !response.session };
}

export async function replaceGuestConversation() {
  return apiFetch<{ conversation: Conversation }>(
    "/conversations/guest/replace",
    { method: "POST" },
  );
}
