import { expect, test, describe } from "bun:test";
import fs from "fs";
import path from "path";

import { retryLastTurnActionFromMessage } from "../lib/chat-retry-actions";

const webRoot = path.resolve(__dirname, "..");

const read = (relativePath: string) =>
  fs.readFileSync(path.join(webRoot, relativePath), "utf-8");

const flattenKeys = (value: unknown, prefix = ""): string[] => {
  if (typeof value !== "object" || value === null) return [prefix];
  return Object.entries(value as Record<string, unknown>).flatMap(([key, child]) =>
    flattenKeys(child, prefix ? `${prefix}.${key}` : key),
  );
};

describe("onboarding strip-out: first use is ordinary chat", () => {
  test("no onboarding gate component exists", () => {
    expect(fs.existsSync(path.join(webRoot, "components/onboarding"))).toBe(false);
  });

  test("home and chat pages do not import or render an onboarding gate", () => {
    const landing = read("app/page.tsx");
    expect(landing).not.toContain("OnboardingGate");
    expect(landing.toLowerCase()).not.toContain("onboarding");
    expect(fs.existsSync(path.join(webRoot, "app/chat/page.tsx"))).toBe(false);
  });

  test("chat surface renders no onboarding goal cards or hidden protocol", () => {
    const chat = read("components/chat/ChatInterface.tsx");
    expect(chat).not.toContain("onboarding-goal-cards");
    expect(chat).not.toContain("onboarding-skip");
    expect(chat).not.toContain("__ONBOARDING_");
    expect(chat.toLowerCase()).not.toContain("onboarding");
  });

  test("chat message rendering has no onboarding marker substitution", () => {
    const message = read("components/chat/ChatMessage.tsx");
    expect(message).not.toContain("__ONBOARDING_");
    expect(message.toLowerCase()).not.toContain("onboarding");
  });

  test("no private-alpha onboarding feature flag remains", () => {
    const flags = read("lib/private-alpha-flags.ts");
    expect(flags).not.toContain("ONBOARDING");
    const envExample = read(".env.local.example");
    expect(envExample).not.toContain("ONBOARDING");
    const playwrightConfig = read("playwright.config.ts");
    expect(playwrightConfig).not.toContain("ONBOARDING");
    const guestQaRunner = read("../scripts/qa/run-guest-experience-qa.sh");
    expect(guestQaRunner).not.toContain("ONBOARDING");
    const guestQaSupport = read("e2e/support/guest-qa.ts");
    expect(guestQaSupport).not.toContain("ONBOARDING");
  });

  test("profile api surface cannot write onboarding state", () => {
    const api = read("lib/argus-api.ts");
    expect(api.toLowerCase()).not.toContain("onboarding");
  });

  test("dev tooling has no onboarding reset", () => {
    const badge = read("components/ui/DevModeBadge.tsx");
    expect(badge.toLowerCase()).not.toContain("onboarding");
  });

  test("locale catalogs carry no onboarding strings and stay key-equal", () => {
    const en = JSON.parse(read("public/locales/en/common.json"));
    const es = JSON.parse(read("public/locales/es-419/common.json"));
    expect(Object.keys(en)).not.toContain("onboarding");
    expect(Object.keys(es)).not.toContain("onboarding");
    const enKeys = flattenKeys(en).sort();
    const esKeys = flattenKeys(es).sort();
    expect(esKeys).toEqual(enKeys);
    expect(enKeys.some((key) => key.toLowerCase().includes("onboarding"))).toBe(false);
  });

  test("investing starter prompts are gone and only caller entries render", () => {
    const emptyChat = read("components/chat/EmptyChatSurface.tsx");
    const starters = read("components/chat/StarterActions.tsx");
    expect(emptyChat).toContain("<StarterActions");
    expect(starters).toContain("if (!workspaceEntries?.length) return null;");
    expect(starters).not.toContain("chat.starter_actions");
    const en = JSON.parse(read("public/locales/en/common.json"));
    const es = JSON.parse(read("public/locales/es-419/common.json"));
    expect(en.chat.starter_actions).toBeUndefined();
    expect(es.chat.starter_actions).toBeUndefined();
  });

  test("chat first paint waits for the authenticated profile language", () => {
    const chat = read("components/chat/ChatInterface.tsx");
    const init = read("components/chat/useInitialChatSession.ts");
    const refreshStart = chat.indexOf("const refreshAccount = useCallback");
    const refreshEnd = chat.indexOf("const [messages, setMessages]", refreshStart);
    const refresh = chat.slice(refreshStart, refreshEnd);
    const languageApply = init.indexOf(
      "await commitShellLanguage(i18n, businessPilotEnabled, meResponse?.user?.language)",
    );
    const establishedFlip = init.indexOf('setProfileState("established")');
    const refreshLanguageApply = refresh.indexOf(
      "await commitShellLanguage(i18n, businessPilotEnabled, nextAccount.user.language)",
    );
    const refreshEstablishedFlip = refresh.indexOf(
      'setProfileState("established")',
    );
    expect(refreshStart).toBeGreaterThan(-1);
    expect(refreshEnd).toBeGreaterThan(refreshStart);
    expect(refreshLanguageApply).toBeGreaterThan(-1);
    expect(refreshEstablishedFlip).toBeGreaterThan(refreshLanguageApply);
    expect(languageApply).toBeGreaterThan(-1);
    expect(establishedFlip).toBeGreaterThan(languageApply);
    expect(chat).toContain(
      'if (profileState === "probing" || profileState === "unavailable") {',
    );
  });

  test("a successful null profile probe never enters authenticated chat", () => {
    const landing = read("app/page.tsx");
    const init = read("components/chat/useInitialChatSession.ts");

    expect(landing).toContain("const meResponse = await getMe()");
    expect(landing).toContain("if (meResponse === null)");
    expect(init).toContain("if (meResponse === null)");
    expect(init.indexOf("if (meResponse === null)")).toBeLessThan(
      init.indexOf('setProfileState("established")'),
    );
  });

  test("an unreachable backend fails closed to the auth-first surface", () => {
    const chat = read("components/chat/ChatInterface.tsx");
    const init = read("components/chat/useInitialChatSession.ts");
    const failClosedBranch = init.indexOf(
      'else if (probeOutcome === "fail_closed") {',
    );
    expect(failClosedBranch).toBeGreaterThan(-1);
    const failClosed = init.slice(failClosedBranch, failClosedBranch + 220);
    expect(failClosed).toContain('setProfileState("unavailable")');
    expect(failClosed).toContain("router.replace(currentAuthLoginPath())");
    expect(chat).toContain(
      'if (profileState === "probing" || profileState === "unavailable") {',
    );
  });

  test("legacy persisted marker content still cannot become a retry action", () => {
    expect(retryLastTurnActionFromMessage("__ONBOARDING_SKIP__")).toBeNull();
    expect(
      retryLastTurnActionFromMessage("__ONBOARDING_GOAL__:test_stock_idea"),
    ).toBeNull();
    expect(retryLastTurnActionFromMessage("Buy AAPL monthly")).not.toBeNull();
  });
});
