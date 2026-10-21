import assert from "node:assert/strict";
import { join } from "node:path";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";

/**
 * The Spanish flag is read once when the test preload imports the API transport,
 * so the DOM test runs in a child `bun test` that starts with the flag on. In
 * that child the spawner is skipped and the DOM test runs; here it is the reverse.
 */
const spanishShipped = process.env.NEXT_PUBLIC_ENABLE_SPANISH === "true";
const originalFetch = globalThis.fetch;
const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
const cleanups: (() => Promise<void>)[] = [];
/** The account as the API holds it; a PATCH rewrites it the way the server would. */
const account: { language: string; locale: string; onboarding: { language_confirmed: boolean } } = { language: "es-419", locale: "es-419", onboarding: { language_confirmed: false } };
const patches: Record<string, unknown>[] = [];

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  Object.defineProperty(window.navigator, "language", { configurable: true, value: "en-US" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === "PATCH") {
      const patch = JSON.parse(String(init.body)) as Record<string, unknown>;
      patches.push(patch);
      Object.assign(account, patch, "language" in patch ? { onboarding: { language_confirmed: true } } : {});
    }
    return Response.json({ user: { id: "settings-owner", display_name: "Test owner", email: "owner@example.test", ...account }, account_kind: "registered", available: false });
  }) as typeof fetch;
});
afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  document.body.innerHTML = "";
});
afterAll(async () => {
  globalThis.fetch = originalFetch;
  if (originalMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
  await GlobalRegistrator.unregister();
});

const button = (text: string) => [...document.body.querySelectorAll("button")].find((item) => item.textContent?.trim() === text);
const settle = (act: (callback: () => Promise<void>) => Promise<void>) => act(async () => { await new Promise((resolve) => setTimeout(resolve, 30)); });

test.skipIf(spanishShipped)("the settings switch is proven in a child run with Spanish shipped", () => {
  const result = Bun.spawnSync({
    cmd: ["bun", "test", import.meta.path],
    cwd: join(import.meta.dir, ".."),
    env: { ...process.env, NEXT_PUBLIC_ENABLE_SPANISH: "true", NEXT_PUBLIC_BUSINESS_PILOT_ENABLED: "true" },
    stderr: "pipe",
    stdout: "pipe",
  });
  const output = result.stdout.toString() + result.stderr.toString();
  assert.equal(result.exitCode, 0, output);
  assert.match(output, / 1 pass/, output);
  assert.match(output, / 0 fail/, output);
});

test.skipIf(!spanishShipped)("Preferencias > Idioma offers English, saves it on the account and shows it at once without a reload", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { ChatWorkspaceProvider } = await import("@/components/chat/ChatWorkspace");
  const { default: ProfileMenu } = await import("@/components/sidebar/ProfileMenu");
  const i18n = createInstance();
  await i18n.init({ lng: "es-419", resources: { en: { translation: english }, "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const anchor = document.createElement("button");
  document.body.appendChild(anchor);
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const workspace = { conversationSurface: "business" } as Parameters<typeof ChatWorkspaceProvider>[0]["value"];
  const render = () => {
    return (
      <I18nextProvider i18n={i18n}>
        <ChatWorkspaceProvider value={workspace}>
          <ProfileMenu isOpen onClose={() => {}} onLogout={() => {}} anchorRef={{ current: anchor }} />
        </ChatWorkspaceProvider>
      </I18nextProvider>
    );
  };
  await act(async () => root.render(render()));
  cleanups.push(() => act(async () => root.unmount()));
  await settle(act);

  await act(async () => button("Preferencias")!.click());
  await act(async () => button("Idioma de la app")!.click());
  const englishChoice = button("English");
  assert.ok(englishChoice, "the language panel offers English on Business");
  assert.ok(button("Español"), "and keeps Spanish beside it");
  await act(async () => englishChoice!.click());
  await settle(act);

  assert.deepEqual(patches, [{ language: "en", locale: "en-US" }]);
  assert.equal(account.language, "en");
  assert.equal(account.onboarding.language_confirmed, true);
  assert.equal(i18n.language, "en");
  assert.ok(button("Preferences"), "the menu reads in English right after the save");
  assert.equal(button("Preferencias"), undefined);
  assert.equal(window.navigator.language, "en-US");
});
