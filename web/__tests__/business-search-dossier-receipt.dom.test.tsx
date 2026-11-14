import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";

// A search hit's receipt preview loads the saved receipt beside the results. A receipt the server no longer
// has (404) says it is gone; any other failure shows the shared retry line, never a guess that it was removed.
const cleanups: (() => Promise<void>)[] = [];
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  document.body.innerHTML = "";
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

function failure(status: number, code: string) {
  return Object.assign(new Error(code), { status, code, requestId: `req-${status}` });
}

async function mount(receipt: BusinessDataSource["receipt"]) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { default: BusinessSearchDossier } = await import("@/components/business-app/BusinessSearchDossier");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  const hit = (await fixture.receipts("all")).find((item) => item.id === "rcpt-ferreteria")!;
  let asked = 0;
  const source: BusinessDataSource = { ...fixture, receipt: (id, signal) => { asked += 1; return receipt(id, signal); } };
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessContext.Provider value={{ source, openPanel: () => undefined } as unknown as BusinessContextValue}>
          <BusinessSearchDossier record={{ kind: "receipt", receipt: { ...hit, dgii_606: null } }} source={source} accounts={[]} />
        </BusinessContext.Provider>
      </I18nextProvider>,
    );
  });
  cleanups.push(async () => { await act(async () => root.unmount()); host.remove(); });
  const settle = async (done: () => boolean, label: string) => {
    for (let i = 0; i < 80 && !done(); i += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    assert.ok(done(), label);
  };
  return { host, settle, asked: () => asked, fixture, text: () => host.textContent ?? "" };
}

describe("a search hit's receipt preview", () => {
  test("a receipt the server no longer has says it is gone, with no Reintentar", async () => {
    const page = await mount(async () => { throw failure(404, "receipt_not_found"); });
    await page.settle(() => page.text().includes("Ese recibo ya no está"), "the gone state shows");
    assert.ok(!page.text().includes("quitado"));
    assert.equal([...page.host.querySelectorAll("button")].find((button) => button.textContent === "Reintentar"), undefined, "no Reintentar");
    assert.equal(page.host.querySelector('[data-testid="error-reference"]'), null);
  });

  test("any other failure shows the shared retry line, and Reintentar loads the receipt", async () => {
    let down = true;
    const page = await mount(async (id, signal) => {
      if (down) throw failure(500, "internal_error");
      const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
      return createFixtureBusinessDataSource({ chatAvailable: false }).receipt(id, signal);
    });
    await page.settle(() => Boolean(page.host.querySelector('[role="alert"]')), "the retry line shows");
    assert.ok(page.host.querySelector('[role="alert"]')?.textContent?.includes("No pudimos actualizar."));
    assert.ok(page.host.querySelector('[data-testid="error-reference"]')?.textContent?.includes("Ref."));
    assert.ok(!page.text().includes("quitado"));
    assert.ok(!page.text().includes("ya no está"));
    down = false;
    const { act } = await import("react");
    const retry = [...page.host.querySelectorAll("button")].find((button) => button.textContent === "Reintentar")!;
    await act(async () => { retry.click(); });
    await page.settle(() => page.text().includes("Recibo original"), "the receipt loads");
    assert.equal(page.asked(), 2);
    assert.equal(page.host.querySelector('[role="alert"]'), null);
  });
});
