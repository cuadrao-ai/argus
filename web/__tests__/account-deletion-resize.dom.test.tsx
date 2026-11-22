import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import { ChatWorkspaceProvider, type ChatWorkspace } from "@/components/chat/ChatWorkspace";
import spanish from "@/public/locales/es-419/common.json";

const copy = spanish.settings.profile.request_deletion;
const originalFetch = globalThis.fetch;
const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
const cleanups: (() => Promise<void>)[] = [];
let deletionReply = () => Response.json({ status: "done" });
let calls: string[] = [];

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  globalThis.fetch = (async (input: unknown, init?: RequestInit) => {
    const path = new URL(String(input), "http://localhost").pathname;
    calls.push(`${init?.method ?? "GET"} ${path}`);
    if (path.endsWith("/account/deletion")) return Response.json({ allowed: true, blockers: [], notices: [] });
    if (path.endsWith("/account/delete")) return deletionReply();
    if (path.endsWith("/feedback")) return Response.json({ success: true });
    throw new Error(`Unexpected mocked request: ${path}`);
  }) as typeof fetch;
});
afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  document.body.innerHTML = "";
  calls = [];
});
afterAll(async () => {
  globalThis.fetch = originalFetch;
  if (originalMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
  await GlobalRegistrator.unregister();
});

const button = (text: string) => [...document.querySelectorAll("button")].find((node) => node.textContent?.trim() === text)!;

async function mountWindow(onAccountDeleted: () => void, onClose: () => void) {
  const { act, useState } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { default: SettingsWindow } = await import("@/components/settings/SettingsWindow");
  const { default: AccountSettings } = await import("@/components/settings/AccountSettings");
  const i18n = createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  function Harness() {
    const [open, setOpen] = useState(true);
    return open ? (
      <SettingsWindow
        sections={["appearance", "account"]}
        renderSection={(panel) => panel === "account" ? (
          <AccountSettings
            profile={null}
            avatar={{ className: "", style: undefined }}
            profileLanguage="es-419"
            lifecycleControls={false}
            onLogout={() => assert.fail("No logout button after deletion")}
            onLeave={() => assert.fail("No navigation after deletion")}
            onAccountDeleted={onAccountDeleted}
            onClose={onClose}
          />
        ) : <div data-testid="other-settings-section" />}
        legalLinks={[]}
        returnFocusRef={{ current: null }}
        onClose={() => { onClose(); setOpen(false); }}
      />
    ) : null;
  }
  await act(async () => root.render(
    <I18nextProvider i18n={i18n}>
      <ChatWorkspaceProvider value={{ conversationSurface: "business" } as ChatWorkspace}>
        <Harness />
      </ChatWorkspaceProvider>
    </I18nextProvider>,
  ));
  cleanups.push(() => act(async () => root.unmount()));
  return act;
}

const replies = {
  success: () => Response.json({ status: "done" }),
  in_progress: () => Response.json({ status: "in_progress", pending: [] }, { status: 202 }),
  requested: () => Response.json({ code: "not_found" }, { status: 404 }),
};

for (const outcome of Object.keys(replies) as (keyof typeof replies)[]) {
  for (const exit of ["close", "Escape"] as const) {
    test(`${outcome}: the answer and hold survive 1280 → 800 → 1280, then ${exit} closes once`, async () => {
      window.happyDOM.setWindowSize({ width: 1280, height: 900 });
      deletionReply = replies[outcome];
      let ended = 0;
      let closed = 0;
      const act = await mountWindow(() => { ended += 1; }, () => { closed += 1; });
      await act(async () => document.querySelector<HTMLButtonElement>('[data-testid="settings-nav-account"]')!.click());
      await act(async () => button(copy.confirm).click());
      await act(async () => button(copy.confirm).click());
      const completedCalls = [...calls];

      for (const width of [1280, 800, 1280]) {
        await act(async () => window.happyDOM.setWindowSize({ width, height: 900 }));
        const answer = document.querySelector('[role="status"]');
        assert.equal(answer?.textContent, copy[outcome], `${width}px retains the ${outcome} answer`);
        const surface = answer!.closest('[role="dialog"]')!;
        assert.equal(surface.querySelector('[data-testid="settings-window-back"]'), null, "the held answer has no back control");
        assert.ok(surface.querySelector('[data-testid="settings-window-close"]'), "the held answer has an exit");
        assert.equal(document.querySelector('[data-testid="account-settings"]'), null);
        assert.equal(document.querySelector('[data-testid="other-settings-section"]'), null);
        const rows = [...document.querySelectorAll<HTMLButtonElement>('[data-testid^="settings-nav-"]')];
        for (const row of rows) {
          assert.ok(row.disabled, "every visible section row is held");
          await act(async () => row.click());
        }
        assert.equal(document.querySelector('[role="status"]')?.textContent, copy[outcome]);
        assert.equal(closed, 0, "resizing never invokes an exit");
        assert.equal(ended, outcome === "requested" ? 0 : 1, "resizing never repeats sign-out");
        assert.deepEqual(calls, completedCalls, "resizing makes no new requests");
      }
      assert.equal(calls.filter((call) => call.endsWith("/account/delete")).length, 1);
      // Also exercise the exit from the phone layout after the round trip.
      if (exit === "close") await act(async () => window.happyDOM.setWindowSize({ width: 800, height: 900 }));
      await act(async () => {
        if (exit === "close") document.querySelector<HTMLButtonElement>('[data-testid="settings-window-close"]')!.click();
        else document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      });
      assert.equal(closed, 1);
      assert.equal(document.querySelector('[role="dialog"]'), null);
      assert.equal(ended, outcome === "requested" ? 0 : 1);
    });
  }
}
