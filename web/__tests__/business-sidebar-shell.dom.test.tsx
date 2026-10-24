import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import spanish from "@/public/locales/es-419/common.json";

const cleanups: (() => Promise<void>)[] = [];

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  document.body.innerHTML = "";
});

afterAll(async () => {
  await GlobalRegistrator.unregister();
});

test("Business settings offer Expanded and Icons only; Personal keeps On hover", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { default: SidebarPreferenceModal } = await import("@/components/settings/SidebarPreferenceModal");
  const i18n = createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  cleanups.push(async () => { await act(async () => root.unmount()); });
  const render = async (business: boolean) => act(async () => root.render(
    <I18nextProvider i18n={i18n}>
      <SidebarPreferenceModal business={business} mode="expanded" onSelect={() => {}} onClose={() => {}} />
    </I18nextProvider>,
  ));
  await render(true);
  assert.match(document.body.textContent ?? "", /Expandida/);
  assert.match(document.body.textContent ?? "", /Solo iconos/);
  assert.doesNotMatch(document.body.textContent ?? "", /Al pasar el cursor/);
  await render(false);
  assert.match(document.body.textContent ?? "", /Al pasar el cursor/);
});
