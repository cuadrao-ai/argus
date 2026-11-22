import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { BandejaGroup, BandejaLabel, ReceiptDetail } from "@/lib/business-api";

mock.module("next/navigation", () => ({
  usePathname: () => "/biz",
  useRouter: () => ({ push: () => {}, replace: () => {}, refresh: () => {}, prefetch: () => {} }),
  useSearchParams: () => new URLSearchParams(),
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const group = (name: BandejaGroup["group"], reason: string | null, label: BandejaLabel): BandejaGroup => ({ group: name, reason, label, draft_id: null, version: null });

/** One receipt opened as the server sent it, with or without a prepared record behind it. The server sends a prepared record the same group as its receipt. */
async function open(receipt: Partial<ReceiptDetail>, prepared: boolean) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
  const ReceiptReviewPanel = (await import("@/components/business-app/ReceiptReviewPanel")).default;
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  const source: BusinessDataSource = {
    ...fixture,
    receipt: async (id, signal) => ({ ...await fixture.receipt(id, signal), draft_id: prepared ? dossierFixtureIds.fiscal : null, delete_available: true, ...receipt }),
    dossier: async (id) => ({ ...structuredClone(await fixture.dossier(id)), delete_available: true, ...(receipt.bandeja_group ? { bandeja_group: receipt.bandeja_group } : {}) }),
    deleteDocument: async (id) => ({ document_id: id, deleted: true }),
  };
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source}>
            <ReceiptReviewPanel target={{ kind: "receipt", id: "rcpt-ferreteria" }} />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  const settle = async (ready: () => boolean) => {
    for (let i = 0; i < 80 && !ready(); i += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    assert.ok(ready(), `the page settled: ${document.body.textContent?.slice(0, 400)}`);
  };
  const click = (element: Element | null) => act(async () => { assert.ok(element); (element as HTMLElement).click(); });
  try {
    await settle(() => Boolean(document.querySelector('[data-testid="delete-document-menu"]')));
    const pill = host.querySelector('[data-testid="dossier-status"] [data-testid="status-pill"]');
    await click(document.querySelector('[data-testid="receipt-more"] > button'));
    await click(document.querySelector('[data-testid="delete-document-menu"]'));
    const state = [...document.querySelectorAll('[role="alertdialog"] [data-testid="document-delete-facts"] dl > div')].find((row) => row.querySelector("dt")?.textContent === "Estado")?.querySelector("dd")?.textContent;
    return { header: pill?.textContent ?? null, label: pill?.getAttribute("data-label") ?? null, dialog: state };
  } finally {
    await act(async () => { root.unmount(); host.remove(); });
    document.body.innerHTML = "";
  }
}

/** The server's Bandeja label decides the status. `status` and `attention` are set against it to prove nothing else is read. An accepted record has no pill; its word stays in the delete dialog. */
const CASES: readonly { name: string; receipt: Partial<ReceiptDetail>; word: string; label: BandejaLabel }[] = [
  { name: "an attention receipt shows the status, not its reason", receipt: { status: "review_ready", attention: null, bandeja_group: group("attention", "missing_ncf", "needs_attention") }, word: "Necesita atención", label: "needs_attention" },
  { name: "an attention receipt with no reason", receipt: { status: "review_ready", attention: null, bandeja_group: group("attention", null, "needs_attention") }, word: "Necesita atención", label: "needs_attention" },
  { name: "a receipt that could not be read", receipt: { status: "review_ready", attention: null, bandeja_group: group("attention", "unreadable", "cant_read") }, word: "No se pudo leer", label: "cant_read" },
  { name: "a receipt being read", receipt: { status: "preparing", attention: null, bandeja_group: group("reading", "reading", "reading") }, word: "Leyendo…", label: "reading" },
  { name: "a Listos receipt", receipt: { status: "review_ready", attention: null, bandeja_group: group("listo", null, "ready") }, word: "Listo para aceptar", label: "ready" },
  { name: "a Listos receipt whose status disagrees", receipt: { status: "needs_attention", attention: "check_details", bandeja_group: group("listo", null, "ready") }, word: "Listo para aceptar", label: "ready" },
];
const ACCEPTED: Partial<ReceiptDetail> = { status: "confirmed", attention: null, bandeja_group: group(null, null, "accepted") };

describe("the receipt's status is the server's Bandeja label, never its reason", () => {
  for (const prepared of [true, false]) {
    for (const { name, receipt, word, label } of CASES) {
      test(`${name}, ${prepared ? "with" : "without"} a prepared record`, async () => {
        const shown = await open(receipt, prepared);
        assert.deepEqual(shown, { header: word, label, dialog: word });
      });
    }
    test(`an accepted receipt has no pill, ${prepared ? "with" : "without"} a prepared record`, async () => {
      const shown = await open(ACCEPTED, prepared);
      assert.deepEqual(shown, { header: null, label: null, dialog: "Aceptado" });
    });
  }
});
