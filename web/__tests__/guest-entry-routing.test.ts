import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import * as landingEntry from "../lib/landing-entry";
import { surfacePath } from "../lib/conversation-surface-guard";

const root = join(import.meta.dir, "..");
const { resolveLandingEntrySurface } = landingEntry;

type ResolveChatEntrySurface = (input: {
  hasEstablishedUser: boolean;
  guestAccessEnabled: boolean;
  guestCaptchaConfigured: boolean;
  businessBuild?: boolean;
}) => "chat" | "auth";

describe("landing entry routing", () => {
  test("resolves the existing session before default-on guest entry", () => {
    expect(
      resolveLandingEntrySurface({
        authMode: "intro",
        guestEntryAvailable: true,
        isCheckingSession: true,
      }),
    ).toBe("loading");
  });

  test("keeps explicit request, login, and signup states on the auth surface", () => {
    for (const authMode of ["request", "login", "signup"] as const) {
      expect(
        resolveLandingEntrySurface({
          authMode,
          guestEntryAvailable: true,
          isCheckingSession: false,
        }),
      ).toBe("auth");
    }
  });

  test("uses guest entry only after an unauthenticated intro request resolves", () => {
    expect(
      resolveLandingEntrySurface({
        authMode: "intro",
        guestEntryAvailable: true,
        isCheckingSession: false,
      }),
    ).toBe("guest");
    expect(
      resolveLandingEntrySurface({
        authMode: "intro",
        guestEntryAvailable: false,
        isCheckingSession: false,
      }),
    ).toBe("auth");
  });

  test("requires both guest gates to render unauthenticated chat", () => {
    const resolveChatEntrySurface = (
      landingEntry as typeof landingEntry & {
        resolveChatEntrySurface?: ResolveChatEntrySurface;
      }
    ).resolveChatEntrySurface;

    expect(resolveChatEntrySurface).toBeFunction();
    if (!resolveChatEntrySurface) return;

    expect(
      resolveChatEntrySurface({
        hasEstablishedUser: false,
        guestAccessEnabled: true,
        guestCaptchaConfigured: true,
      }),
    ).toBe("chat");
    for (const rollback of [
      { guestAccessEnabled: false, guestCaptchaConfigured: true },
      { guestAccessEnabled: true, guestCaptchaConfigured: false },
      { guestAccessEnabled: false, guestCaptchaConfigured: false },
    ]) {
      expect(
        resolveChatEntrySurface({
          hasEstablishedUser: false,
          ...rollback,
        }),
      ).toBe("auth");
    }
    expect(
      resolveChatEntrySurface({
        hasEstablishedUser: true,
        guestAccessEnabled: false,
        guestCaptchaConfigured: false,
      }),
    ).toBe("chat");
  });

  test("uses the shared chat-entry decision without bouncing guests to root", () => {
    const chatPage = readFileSync(join(root, "app/chat/page.tsx"), "utf-8");

    expect(chatPage).toContain("resolveChatEntrySurface");
    expect(chatPage).not.toContain('redirect("/")');
    expect(chatPage).toContain("authLoginPathFromSearch");
    expect(chatPage).toContain('authLoginPathFromSearch(await searchParams, "/chat")');
    expect(chatPage).toContain("<ChatInterface />");
  });
});

describe("a Cuadrao Business build has no guest chat", () => {
  test("signed out goes to login even with both guest gates open; signed in still reaches chat", () => {
    const resolveChatEntrySurface = landingEntry.resolveChatEntrySurface;
    expect(resolveChatEntrySurface({ hasEstablishedUser: false, guestAccessEnabled: true, guestCaptchaConfigured: true, businessBuild: true })).toBe("auth");
    expect(resolveChatEntrySurface({ hasEstablishedUser: true, guestAccessEnabled: true, guestCaptchaConfigured: true, businessBuild: true })).toBe("chat");
    expect(resolveChatEntrySurface({ hasEstablishedUser: false, guestAccessEnabled: true, guestCaptchaConfigured: true, businessBuild: false })).toBe("chat");
  });

  test("the pages wire the build flag: /chat sends everyone to the Business shell, the root page has no guest entry, and every chat-bound caller goes to the Business equivalent", () => {
    const chatPage = readFileSync(join(root, "app/chat/page.tsx"), "utf-8");
    // Signed in or not: on a Business build the old chat page is not a surface.
    expect(chatPage).toContain("if (businessPilotEnabled) redirect(businessShellPath(await searchParams));");
    expect(chatPage.indexOf("if (businessPilotEnabled) redirect(")).toBeLessThan(chatPage.indexOf("supabase.auth.getUser()"));
    expect(chatPage).toContain("businessBuild: businessPilotEnabled");
    expect(surfacePath("consumer", true)).toBe("/biz");
    expect(surfacePath("business", true)).toBe("/biz");
    expect(surfacePath("consumer", false)).toBe("/chat");
    const followup = readFileSync(join(root, "components/receipt/ReceiptFollowup.tsx"), "utf-8");
    expect(followup).toContain("router.push(signedInHomePath())");
    expect(followup).not.toContain("currentChatPath()");
    const rootPage = readFileSync(join(root, "app/page.tsx"), "utf-8");
    expect(rootPage).toContain("!businessPilotEnabled && !profileProbeFailedClosed && guestAccessEnabled && guestCaptchaConfigured");
    const security = readFileSync(join(root, "app/account/security/page.tsx"), "utf-8");
    expect(security).toContain("href={signedInHomePath()}");
    expect(security).not.toContain('href="/chat"');
    const chat = readFileSync(join(root, "components/chat/ChatInterface.tsx"), "utf-8");
    expect(chat).toContain("window.location.assign(signedInHomePath())");
    expect(chat).not.toContain('window.location.assign("/chat")');
  });
});
