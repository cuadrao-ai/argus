import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { guestLandingHref, sessionAdmitted } from "../lib/landing-entry";
import { guestAutoPickAllowed } from "../components/chat/useInitialChatSession";

const root = join(import.meta.dir, "..");
const source = (path: string) => readFileSync(join(root, path), "utf-8");

describe("Business has no guest mode", () => {
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
    expect(rootPage).toContain("if (!sessionAdmitted(meResponse.account_kind, businessPilotEnabled)) {");
    expect(rootPage.indexOf("await logoutFromApi().catch(() => undefined);")).toBeGreaterThan(rootPage.indexOf("if (!sessionAdmitted("));
    const bizPage = source("app/biz/page.tsx");
    expect(bizPage).toContain("if (error || !data.user || data.user.is_anonymous) {");
    const hook = source("components/chat/useInitialChatSession.ts");
    expect(hook).toContain('meResponse?.account_kind === "guest" && guestAutoPickAllowed(surface)');
    const guard = source("components/chat/ConversationShellGuard.tsx");
    expect(guard).toContain("conversationExitHref(window.location.href, conversationId, target)");
    expect(guard).not.toContain("conversationShellHref(");
    const app = source("components/business-app/BusinessApp.tsx");
    expect(app).toContain("<ConversationUnavailableNotice />");
    expect(app.indexOf("<ConversationShellGuard />")).toBeGreaterThanOrEqual(0);
    const expired = source("components/guest/ExpiredGuestSession.tsx");
    expect(expired).not.toContain('window.location.assign("/chat")');
    // A restarted guest goes to the guest landing; a person who signed in goes where sign-in goes.
    expect((expired.match(/guestLandingHref\(businessBuild\)/g) ?? []).length).toBe(1);
    expect(expired).toContain("window.location.assign(postAuthPath(businessBuild))");
  });
});

describe("the expired guest screen on a Business build", () => {
  async function render(businessBuild: boolean) {
    const { createElement } = await import("react");
    const { renderToStaticMarkup } = await import("react-dom/server");
    const i18next = (await import("i18next")).default;
    const { I18nextProvider } = await import("react-i18next");
    const spanish = (await import("../public/locales/es-419/common.json")).default;
    const { default: ExpiredGuestSession } = await import("../components/guest/ExpiredGuestSession");
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
    return renderToStaticMarkup(createElement(I18nextProvider, { i18n }, createElement(ExpiredGuestSession, { publicAccountAccessEnabled: false, businessBuild })));
  }

  test("offers no new temporary chat; Iniciar sesión becomes the one primary action", async () => {
    const business = await render(true);
    expect(business).not.toContain(">Iniciar un nuevo chat temporal<");
    expect(business).toContain(">Iniciar sesión<");
    expect(business).toMatch(/<button[^>]*bg-black[^>]*>Iniciar sesión<\/button>/);
    const consumer = await render(false);
    expect(consumer).toContain(">Iniciar un nuevo chat temporal<");
    expect(consumer).toMatch(/<button[^>]*bg-black[^>]*>Iniciar un nuevo chat temporal<\/button>/);
  });
});
