import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { BusinessCapture } from "@/lib/business-api";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";

// A search hit's receipt or note preview loads the saved record beside the results. A record the server no longer
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

async function mount(override: Partial<Pick<BusinessDataSource, "receipt" | "dossier">>, kind: "receipt" | "note" = "receipt") {
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
  const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
  const hit = (await fixture.receipts("all")).find((item) => item.id === "rcpt-ferreteria")!;
  const note = { draft_id: dossierFixtureIds.ready, version: 1, revision: 1, source_id: "note-1", text: "Compra de cemento", received_at: "2026-11-10T14:00:00Z", review_state: "open" } as BusinessCapture;
  let asked = 0;
  const custom = { ...fixture, ...override };
  const source: BusinessDataSource = { ...custom, receipt: (id, signal) => { asked += 1; return custom.receipt(id, signal); }, dossier: (id) => { asked += 1; return custom.dossier(id); } };
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessContext.Provider value={{ source, openPanel: () => undefined } as unknown as BusinessContextValue}>
          <BusinessSearchDossier record={kind === "note" ? { kind: "note", note } : { kind: "receipt", receipt: { ...hit, dgii_606: null } }} source={source} accounts={[]} />
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
    const page = await mount({ receipt: async () => { throw failure(404, "receipt_not_found"); } });
    await page.settle(() => page.text().includes("Ese recibo ya no está"), "the gone state shows");
    assert.ok(!page.text().includes("quitado"));
    assert.equal([...page.host.querySelectorAll("button")].find((button) => button.textContent === "Reintentar"), undefined, "no Reintentar");
    assert.equal(page.host.querySelector('[data-testid="error-reference"]'), null);
  });

  test("any other failure shows the shared retry line, and Reintentar loads the receipt", async () => {
    let down = true;
    const page = await mount({ receipt: async (id, signal) => {
      if (down) throw failure(500, "internal_error");
      const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
      return createFixtureBusinessDataSource({ chatAvailable: false }).receipt(id, signal);
    } });
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

describe("a search hit's note preview", () => {
  test("a record the server no longer has says it is gone, with no Reintentar", async () => {
    const page = await mount({ dossier: async () => { throw failure(404, "draft_not_found"); } }, "note");
    await page.settle(() => page.text().includes("Este registro no está disponible."), "the gone state shows");
    assert.equal(page.host.querySelector('[role="alert"]'), null);
    assert.equal([...page.host.querySelectorAll("button")].find((button) => button.textContent === "Reintentar"), undefined, "no Reintentar");
    assert.equal(page.host.querySelector('[data-testid="error-reference"]'), null);
  });

  test("the note shows its state and never a revision number, before and after its record loads", async () => {
    const page = await mount({}, "note");
    assert.doesNotMatch(page.text(), /Revisi[oó]n \d/i);
    await page.settle(() => !page.host.querySelector('[aria-busy="true"]') && page.asked() === 1, "the record loads");
    assert.ok(page.text().includes("Compra de cemento"));
    assert.doesNotMatch(page.text(), /Revisi[oó]n \d/i);
  });

  test("no locale keeps the revision line", async () => {
    for (const language of ["es-419", "en"]) {
      const words = (await import(`@/public/locales/${language}/common.json`)).default as { business: { dossier: Record<string, unknown> } };
      assert.equal("revision" in words.business.dossier, false, language);
    }
  });

  test("any other failure shows the shared retry line, and Reintentar loads the record", async () => {
    let down = true;
    const page = await mount({ dossier: async (id) => {
      if (down) throw failure(500, "internal_error");
      const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
      return createFixtureBusinessDataSource({ chatAvailable: false }).dossier(id);
    } }, "note");
    await page.settle(() => Boolean(page.host.querySelector('[role="alert"]')), "the retry line shows");
    assert.ok(page.host.querySelector('[role="alert"]')?.textContent?.includes("No pudimos actualizar."));
    assert.ok(page.host.querySelector('[data-testid="error-reference"]')?.textContent?.includes("Ref."));
    assert.ok(!page.text().includes("no está disponible"));
    down = false;
    const { act } = await import("react");
    const retry = [...page.host.querySelectorAll("button")].find((button) => button.textContent === "Reintentar")!;
    await act(async () => { retry.click(); });
    await page.settle(() => !page.host.querySelector('[role="alert"]') && !page.host.querySelector('[aria-busy="true"]') && page.asked() === 2, "the record loads");
    assert.equal(page.host.querySelector('[data-testid="error-reference"]'), null);
  });
});
