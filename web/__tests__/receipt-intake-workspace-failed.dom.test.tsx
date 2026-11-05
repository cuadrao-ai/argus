import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import { SKELETON_DELAY_MS } from "@/components/business-app/business-skeletons";
import ReceiptIntakeDialog from "@/components/business-app/ReceiptIntakeDialog";
import { ReceiptUploadQueue } from "@/components/business-app/receipt-upload-queue";
import spanish from "@/public/locales/es-419/common.json";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

/** Agregar's sheet before the business's own workspace has arrived, past the wait after which loading paints. */
async function renderIntake(records: Record<string, unknown>, reload: () => void = () => undefined) {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const context = {
    source: {},
    records: { workspace: null, overview: null, inbox: null, notes: null, notesError: false, notesTruncated: false, emails: null, emailsError: false, error: false, closed: false, serverReference: null, ...records },
    bridge: null,
    reload,
  } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessContext.Provider value={context}>
          <ReceiptIntakeDialog target="inbox" queue={new ReceiptUploadQueue(async () => { throw new Error("unused"); }, () => undefined)} onClose={() => undefined} onReview={() => undefined} />
        </BusinessContext.Provider>
      </I18nextProvider>,
    );
  });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, SKELETON_DELAY_MS + 50)); });
  return async () => {
    await act(async () => root.unmount());
    host.remove();
  };
}

const loading = () => document.querySelector('[data-testid="business-loading"]');

test("while the business loads, Agregar shows it loading", async () => {
  const unmount = await renderIntake({});
  try {
    assert.ok(loading());
    assert.equal(document.querySelector('[data-testid="receipt-intake-error"]'), null);
  } finally {
    await unmount();
  }
});

test("a closed business shows its notice in Agregar, not a spinner", async () => {
  const unmount = await renderIntake({ closed: true });
  try {
    assert.ok(document.querySelector('[data-testid="business-home-closed"]'));
    assert.equal(loading(), null);
  } finally {
    await unmount();
  }
});

for (const failure of [
  { name: "a failed load", records: { error: true } },
  { name: "a server error", records: { serverReference: "REF-1234" } },
]) {
  test(`after ${failure.name} of the business, Agregar says so with Reintentar instead of loading forever`, async () => {
    let reloads = 0;
    const unmount = await renderIntake(failure.records, () => { reloads += 1; });
    try {
      const error = document.querySelector('[data-testid="receipt-intake-error"]');
      assert.ok(error, "the sheet shows the error");
      assert.equal(error.getAttribute("role"), "alert");
      assert.match(error.textContent ?? "", /No pudimos cargar tu negocio/);
      assert.equal(loading(), null, "nothing is left loading");
      const retry = [...error.querySelectorAll("button")].find((button) => button.textContent === "Reintentar");
      assert.ok(retry, "Reintentar is offered");
      await act(async () => retry.click());
      assert.equal(reloads, 1, "Reintentar loads the business again");
    } finally {
      await unmount();
    }
  });
}
