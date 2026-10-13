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
