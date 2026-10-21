import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { ReceiptRow } from "@/components/business-app/BusinessInboxPanel";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

test("recovery labels follow a language change without losing the receipt or its actions", async () => {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { en: { translation: english }, "es-419": { translation: spanish } } });
  const receipt = await createFixtureBusinessDataSource().receipt("rcpt-unknown");
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  let opened = 0;
  let retried = 0;
  try {
    await act(async () => root.render(<I18nextProvider i18n={i18n}><ul><ReceiptRow receipt={receipt} onOpen={() => { opened++; }} onRetry={async () => { retried++; }} /></ul></I18nextProvider>));
    const button = (label: string) => {
      const found = [...host.querySelectorAll("button")].find((item) => item.textContent === label);
      assert.ok(found, `The row must offer ${label}`);
      return found;
    };
    button("Escribir datos");
    button("Reintentar");
    await act(async () => { await i18n.changeLanguage("en"); });
    assert.ok(!host.textContent?.includes("Escribir datos"));
    await act(async () => button("Record expense").click());
    await act(async () => button("Retry").click());
    assert.equal(opened, 1);
    assert.equal(retried, 1);
    assert.ok(host.textContent?.includes(receipt.filename!));
    await act(async () => { await i18n.changeLanguage("es-419"); });
    button("Escribir datos");
    button("Reintentar");
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});
