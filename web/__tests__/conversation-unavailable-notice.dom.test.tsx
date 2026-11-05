import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

let search = "";
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(search),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function mount(query: string) {
  search = query;
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { default: ConversationUnavailableNotice } = await import("@/components/business-app/ConversationUnavailableNotice");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<I18nextProvider i18n={i18n}><ConversationUnavailableNotice /></I18nextProvider>); });
  return { act, root, host };
}

describe("the not-available notice in the Business app", () => {
  test("renders one sentence and one link to /biz when the address names it, and nothing otherwise", async () => {
    const shown = await mount("notice=conversation_unavailable");
    const notice = shown.host.querySelector('[data-testid="conversation-unavailable"]');
    assert.ok(notice);
    assert.equal(notice.getAttribute("role"), "status");
    assert.ok(notice.textContent?.includes("Esta conversación no está disponible en Cuadrao Business."));
    const link = notice.querySelector("a");
    assert.equal(link?.getAttribute("href"), "/biz");
    assert.equal(link?.textContent, "Ir a Cuadrao Business");
    await shown.act(async () => shown.root.unmount());
    const hidden = await mount("view=inbox");
    assert.equal(hidden.host.querySelector('[data-testid="conversation-unavailable"]'), null);
    await hidden.act(async () => hidden.root.unmount());
  });
});
