import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import ReceptionArrivalRow from "@/components/business-app/recepcion/ReceptionArrivalRow";
import { defaultReceptionPreferences } from "@/components/business-app/recepcion/ReceptionControls";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

test("a problem row's state follows a language change without losing the receipt, and the row opens its dossier", async () => {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { en: { translation: english }, "es-419": { translation: spanish } } });
  const receipt = await createFixtureBusinessDataSource().receipt("rcpt-unknown");
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  let opened = 0;
  const state = () => host.querySelector('[data-testid="status-pill"]')?.textContent ?? "";
  const row = { kind: "receipt" as const, id: receipt.id, receivedAt: receipt.received_at, source: receipt.channel, receipt, sender: null };
  const context = { chosen: null, source: createFixtureBusinessDataSource() } as unknown as BusinessContextValue;
  try {
    await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><ul><ReceptionArrivalRow row={row} panel={{ kind: "inbox" }} openPanel={() => undefined} preferences={defaultReceptionPreferences()} selectable={false} checked={false} unseen={false} inspecting={false} onCheck={() => undefined} onSeen={() => undefined} onInspect={() => { opened++; }} /></ul></BusinessContext.Provider></I18nextProvider>));
    assert.match(state(), /^Necesita atención$/);
    assert.ok(host.textContent?.includes("No recuperamos la lectura"));
    await act(async () => { await i18n.changeLanguage("en"); });
    assert.ok(host.textContent?.includes("Reading result lost"));
    assert.match(state(), /^Needs attention$/);
    assert.ok(host.textContent?.includes(receipt.filename!));
    await act(async () => host.querySelector<HTMLButtonElement>("button")!.click());
    assert.equal(opened, 1);
    await act(async () => { await i18n.changeLanguage("es-419"); });
    assert.match(state(), /^Necesita atención$/);
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});
