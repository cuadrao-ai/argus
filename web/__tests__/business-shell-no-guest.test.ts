import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { guestLandingHref, sessionAdmitted } from "../lib/landing-entry";
import { guestAutoPickAllowed } from "../components/chat/useInitialChatSession";
import { classifyBusinessIdentity } from "../lib/session-recovery";

const root = join(import.meta.dir, "..");
const source = (path: string) => readFileSync(join(root, path), "utf-8");

describe("Business has no guest mode", () => {
  test.each([
    ["missing", null],
    ["anonymous", { id: "guest", is_anonymous: true }],
  ] as const)("the shared Business identity guard refuses a %s user", async (_kind, user) => {
    expect(await classifyBusinessIdentity(async () => ({ data: { user }, error: null }))).toBe("missing");
  });

  test("a guest session is admitted on a consumer build and treated as signed out on a Business build; registered accounts enter either way", () => {
    expect(sessionAdmitted("guest", false)).toBe(true);
    expect(sessionAdmitted("guest", true)).toBe(false);
    expect(sessionAdmitted("registered", true)).toBe(true);
    expect(sessionAdmitted(undefined, true)).toBe(true);
  });

  test("an expired or restarted guest goes to the guest chat on a consumer build and to login on a Business build", () => {
    expect(guestLandingHref(false)).toBe("/chat");
    expect(guestLandingHref(true)).toBe("/?auth=login");
  });

  test("a guest's latest Personal conversation is never auto-picked on the Business shell or on the notice address", () => {
    expect(guestAutoPickAllowed("personal", "")).toBe(true);
    expect(guestAutoPickAllowed("personal", "?view=chat")).toBe(true);
    expect(guestAutoPickAllowed("business", "")).toBe(false);
    expect(guestAutoPickAllowed("personal", "?notice=conversation_unavailable")).toBe(false);
  });

  test("the pages and the shell are wired to those rules (CI runs no fixture e2e, so the wiring is pinned here)", () => {
    const rootPage = source("app/page.tsx");
    expect(rootPage).toContain("if (!sessionAdmitted(meResponse.account_kind, true)) {");
    expect(rootPage.indexOf("await logoutFromApi().catch(() => undefined);")).toBeGreaterThan(rootPage.indexOf("if (!sessionAdmitted("));
    const bizPage = source("app/biz/page.tsx");
    expect(bizPage).toContain("await classifyBusinessIdentity(");
    expect(bizPage).toMatch(/if \(outcome === "missing"\)\s*\{\s*redirect\(authLoginPathFromSearch/);
    const hook = source("components/chat/useInitialChatSession.ts");
    expect(hook).toContain('meResponse?.account_kind === "guest" && guestAutoPickAllowed(surface)');
    const guard = source("components/chat/ConversationShellGuard.tsx");
    expect(guard).toContain("conversationExitHref(window.location.href, conversationId, target)");
    expect(guard).not.toContain("conversationShellHref(");
    const app = source("components/business-app/BusinessApp.tsx");
    expect(app).toContain("<ConversationUnavailableNotice />");
    expect(app.indexOf("<ConversationShellGuard />")).toBeGreaterThanOrEqual(0);
    expect(source("app/page.tsx")).not.toContain("GuestEntry");
    expect(source("components/chat/ChatInterface.tsx")).not.toContain("ExpiredGuestSession");
  });
});
