import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

// The footer shows only the controls that change something for this many records.
const cases = [
  { count: 0, pageSize: 25, pages: 1, picker: false, arrows: false },
  { count: 1, pageSize: 25, pages: 1, picker: false, arrows: false },
  { count: 25, pageSize: 25, pages: 1, picker: false, arrows: false },
  { count: 40, pageSize: 50, pages: 1, picker: true, arrows: false },
  { count: 60, pageSize: 25, pages: 3, picker: true, arrows: true },
] as const;

test("the shared footer shows a control only when it has an effect", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } } });
  const Pagination = (await import("@/components/business-app/transacciones/RecordsPaginationControls")).default;
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  const changes: number[] = [];
  try {
    for (const { count, pageSize, pages, picker, arrows } of cases) {
      const label = `${count} records at ${pageSize} per page`;
      await act(async () => { root.render(<I18nextProvider i18n={i18n}><Pagination count={count} page={1} pages={pages} pageSize={pageSize} rangeLabel={`${count} documentos`} onPageChange={page => changes.push(page)} onPageSizeChange={() => {}} /></I18nextProvider>); });
      assert.equal(host.querySelector('[data-testid="records-count"]')?.textContent, `${count} documentos`, label);
      assert.equal(Boolean(host.querySelector('button[aria-haspopup="dialog"]')), picker, `${label}: page-size choice`);
      assert.equal(Boolean(host.querySelector("nav")), arrows, `${label}: page arrows`);
    }
    await act(async () => { host.querySelector<HTMLButtonElement>('button[aria-label="Página 2"]')!.click(); });
    assert.deepEqual(changes, [2]);
    await act(async () => { root.render(<I18nextProvider i18n={i18n}><Pagination loading count={0} page={1} pages={1} pageSize={25} rangeLabel="" onPageChange={() => {}} onPageSizeChange={() => {}} /></I18nextProvider>); });
    assert.equal(host.querySelector('[data-testid="records-count"]'), null, "the count waits for the server");
    assert.equal(host.querySelector('button[aria-haspopup="dialog"], nav'), null, "no control before the count is known");
  } finally { await act(async () => { root.unmount(); host.remove(); }); }
});
