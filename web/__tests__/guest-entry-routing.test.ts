import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import * as landingEntry from "../lib/landing-entry";
import { conversationExitHref, surfacePath } from "../lib/conversation-surface-guard";
import { receiptFollowupTarget } from "../lib/landing-intent";

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

  test("the root gate: no guest entry on a Business build, and only with the probe open and both guest gates on elsewhere", () => {
    const open = { probeFailedClosed: false, guestAccessEnabled: true, guestCaptchaConfigured: true };
    expect(landingEntry.guestEntryAvailable({ ...open, businessBuild: true })).toBe(false);
    expect(landingEntry.guestEntryAvailable({ ...open, businessBuild: false })).toBe(true);
    expect(landingEntry.guestEntryAvailable({ ...open, businessBuild: false, probeFailedClosed: true })).toBe(false);
    expect(landingEntry.guestEntryAvailable({ ...open, businessBuild: false, guestAccessEnabled: false })).toBe(false);
    expect(landingEntry.guestEntryAvailable({ ...open, businessBuild: false, guestCaptchaConfigured: false })).toBe(false);
    const rootPage = readFileSync(join(root, "app/page.tsx"), "utf-8");
    expect(rootPage).toContain("guestEntryAvailable: guestEntryAvailable({ businessBuild: businessPilotEnabled,");
  });

  test("a Personal conversation on a Business build goes nowhere but the notice: the page stays, the conversation is dropped, and no shell can ask for it again", () => {
    // Each surface still has one shell by name.
    expect(surfacePath("personal")).toBe("/chat");
    expect(surfacePath("business")).toBe("/biz");
    const here = "http://localhost/biz?conversation=c1&message=m2";
    const exit = conversationExitHref(here, "c1", "personal", true);
    expect(exit).toBe("/biz?notice=conversation_unavailable");
    expect(exit).not.toContain("conversation=");
    // Applying the exit again yields the same address: a fixed point, never a loop.
    expect(conversationExitHref(`http://localhost${exit}`, "c1", "personal", true)).toBe(exit);
    // A Business conversation on a Business build, and either on a consumer build, go to their own shell with the id.
    expect(conversationExitHref("http://localhost/chat?conversation=c1", "c1", "business", true)).toBe("/biz?conversation=c1");
    expect(conversationExitHref(here, "c1", "personal", false)).toBe("/chat?conversation=c1&message=m2");
    expect(conversationExitHref("http://localhost/chat?conversation=c1", "c1", "business", false)).toBe("/biz?conversation=c1");
  });

  test("a public-receipt follow-up never auto-sends into a Business conversation", () => {
    expect(receiptFollowupTarget(true)).toEqual({ send: false, href: "/biz?view=inbox" });
    expect(receiptFollowupTarget(false).send).toBe(true);
    expect(receiptFollowupTarget(false).href).toMatch(/^\/chat/);
    const followup = readFileSync(join(root, "components/receipt/ReceiptFollowup.tsx"), "utf-8");
    expect(followup.indexOf("if (!target.send) { router.push(target.href); return; }")).toBeLessThan(followup.indexOf("saveReceiptFollowup("));
  });

  test("the pages wire the build flag: /chat sends everyone to the Business shell; the Security link and the reload button use the signed-in home (source pins: rendering those pages needs the whole account shell)", () => {
    const chatPage = readFileSync(join(root, "app/chat/page.tsx"), "utf-8");
    // Signed in or not: on a Business build the old chat page is not a surface.
    expect(chatPage).toContain("if (businessPilotEnabled) redirect(businessShellPath(await searchParams));");
    expect(chatPage.indexOf("if (businessPilotEnabled) redirect(")).toBeLessThan(chatPage.indexOf("supabase.auth.getUser()"));
    expect(chatPage).toContain("businessBuild: businessPilotEnabled");
    const security = readFileSync(join(root, "app/account/security/page.tsx"), "utf-8");
    expect(security).toContain("href={signedInHomePath()}");
    expect(security).not.toContain('href="/chat"');
    const chat = readFileSync(join(root, "components/chat/ChatInterface.tsx"), "utf-8");
    expect(chat).toContain("window.location.assign(signedInHomePath())");
    expect(chat).not.toContain('window.location.assign("/chat")');
  });
});
