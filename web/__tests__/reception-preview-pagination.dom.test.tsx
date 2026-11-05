import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

test("shared pagination keeps existing defaults and supports the inbox single-page count", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } } });
  const Pagination = (await import("@/components/business-app/transacciones/RecordsPaginationControls")).default;
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  const changes: number[] = [];
  const render = async (pages: number, hideSinglePage = false) => act(async () => { root.render(<I18nextProvider i18n={i18n}><Pagination page={1} pages={pages} pageSize={25} rangeLabel="1–9 de 9 documentos" onPageChange={page => changes.push(page)} onPageSizeChange={() => {}} hideSinglePage={hideSinglePage} /></I18nextProvider>); });
  try {
    await render(1);
    assert.ok(host.querySelector("nav"), "existing callers retain their single-page navigation");
    assert.equal(host.querySelector<HTMLButtonElement>('button[aria-label="Página anterior"]')?.disabled, true);
    await render(1, true);
    assert.equal(host.querySelector("nav"), null);
    assert.equal(host.querySelector('[data-testid="records-count"]')?.textContent, "1–9 de 9 documentos");
    assert.ok(host.querySelector('button[aria-haspopup="dialog"]'), "page-size choice remains available");
    await render(3, true);
    await act(async () => { host.querySelector<HTMLButtonElement>('button[aria-label="Página 2"]')!.click(); });
    assert.deepEqual(changes, [2]);
  } finally { await act(async () => { root.unmount(); host.remove(); }); }
});
