export type LandingAuthMode = "intro" | "request" | "signup" | "login";

export type LandingEntrySurface = "loading" | "guest" | "auth";

export type ChatEntrySurface = "chat" | "auth";

export function resolveLandingEntrySurface(input: {
  authMode: LandingAuthMode;
  guestEntryAvailable: boolean;
  isCheckingSession: boolean;
}): LandingEntrySurface {
  if (input.isCheckingSession) return "loading";
  if (input.authMode !== "intro") return "auth";
  return input.guestEntryAvailable ? "guest" : "auth";
}

export function resolveChatEntrySurface(input: {
  hasEstablishedUser: boolean;
  guestAccessEnabled: boolean;
  guestCaptchaConfigured: boolean;
  /** A Cuadrao Business build: signed-out visitors always go to login, never to guest chat. */
  businessBuild?: boolean;
}): ChatEntrySurface {
  if (input.hasEstablishedUser) return "chat";
  if (input.businessBuild) return "auth";
  return input.guestAccessEnabled && input.guestCaptchaConfigured
    ? "chat"
    : "auth";
}

/** Whether the signed-out front door may offer guest chat: never on a Business build, and only when the probe did not fail closed and both guest gates are open. */
export function guestEntryAvailable(input: { businessBuild: boolean; probeFailedClosed: boolean; guestAccessEnabled: boolean; guestCaptchaConfigured: boolean }): boolean {
  return !input.businessBuild && !input.probeFailedClosed && input.guestAccessEnabled && input.guestCaptchaConfigured;
}

/** Whether a session that passed the profile probe may enter: on a Business build a guest session is treated as signed out (Business has no guest mode). */
export function sessionAdmitted(accountKind: "guest" | "registered" | undefined, businessBuild: boolean): boolean {
  return !(businessBuild && accountKind === "guest");
}

/** Where an expired or restarted guest goes: the guest chat on a consumer build; login on a Business build, which has no guest mode. */
export function guestLandingHref(businessBuild: boolean): string {
  return businessBuild ? "/?auth=login" : "/chat";
}
