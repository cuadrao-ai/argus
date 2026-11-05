import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import { useState } from "react";
import { ChatWorkspaceProvider, type ChatWorkspace } from "@/components/chat/ChatWorkspace";
import spanish from "@/public/locales/es-419/common.json";

const cleanups: Array<() => Promise<void>> = [];

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  document.body.innerHTML = "";
});

afterAll(async () => {
  await GlobalRegistrator.unregister();
});

test("the phone header opens Ajustes and can sign out, without a menu button", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { default: BusinessPhoneAccount } = await import("@/components/business-app/foundation/BusinessPhoneAccount");
  const i18n = createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const signedOut: string[] = [];
  function PhoneShell() {
    const [request, setRequest] = useState(0);
    return (
      <I18nextProvider i18n={i18n}>
        <ChatWorkspaceProvider value={{ id: "business", conversationSurface: "business" } as ChatWorkspace}>
          <button type="button" onClick={() => setRequest((value) => value + 1)}>Abrir por atajo</button>
          <BusinessPhoneAccount onLogout={() => { signedOut.push("out"); }} settingsOpenRequest={request} />
        </ChatWorkspaceProvider>
      </I18nextProvider>
    );
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<PhoneShell />); });
  cleanups.push(() => act(async () => root.unmount()));
  const account = host.querySelector('[data-testid="business-phone-account"]')!;
  const settings = account.querySelector('[data-testid="header-profile-trigger"]') as HTMLButtonElement;
  assert.equal(settings?.getAttribute("aria-label"), "Ajustes");
  assert.equal(settings.className.includes("h-11"), true);
  assert.equal(host.querySelector('[data-testid="chat-shell-menu-trigger"]'), null);
  await act(async () => { settings.click(); });
  const signOut = [...document.querySelectorAll("button")].find((button) => button.textContent?.includes("Cerrar sesión")) as HTMLButtonElement;
  assert.ok(signOut, "sign out is in the account menu");
  await act(async () => { signOut.click(); });
  assert.deepEqual(signedOut, ["out"]);
  await act(async () => { (host.querySelector("button") as HTMLButtonElement).click(); });
  assert.ok([...document.querySelectorAll("button")].some((button) => button.textContent?.includes("Cerrar sesión")));
});
