import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { ReceiptSummary } from "@/lib/business-api";
import type { BusinessEmailDelivery } from "@/lib/business-email";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const HINT = "Guardado, sin leer. Pulsa «Preparar con IA» para que Cuadrao lo lea, o complétalo tú.";

const receipt = (over: Partial<ReceiptSummary>): ReceiptSummary =>
  ({ id: "rcpt-1", channel: "web", filename: "recibo-prueba-ferreteria.pdf", source_text: null, media_type: "application/pdf", size_bytes: 70, received_at: "2026-10-13T17:14:00Z", status: "saved", error_code: null, attention: null, duplicate_of: null, replayed: false, preparable: true, enterable: true, read_pending: false, expense_id: null, merchant: null, occurred_on: null, amount: null, currency: null, category_id: null, account_id: null, email_delivery_ids: ["d1"], email_original: false, missing_fields: [], version: 0, draft_id: null, ...over } as unknown as ReceiptSummary);

const delivery: BusinessEmailDelivery = {
  id: "d1", state: "captured", received_at: "2026-10-13T17:14:00Z", updated_at: "2026-10-13T17:14:00Z", original_document_id: null, retryable: false, subject: "Factura 0041", sender: "ventas@ferreteria.example", sent_at: null, error_code: null,
  parts: [{ id: "1.2", filename: "recibo-prueba-ferreteria.pdf", media_type: "application/pdf", state: "captured", document_id: "rcpt-1", error_code: null }],
};

async function mount(node: (React: typeof import("react")) => import("react").ReactElement, inbox: ReceiptSummary[]) {
  const React = await import("react");
  const { act } = React;
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const value = {
    source: { emailIntake: async () => ({ enabled: true, receiving_address: "recibos-ab12@example.test" }), emailDeliveries: async () => [delivery], emailDelivery: async () => ({ ...delivery, text_body: "Adjunto" }) },
    records: { inbox, notes: [], notesError: false, notesTruncated: false, emails: [delivery], emailsError: false, workspace: null, overview: null, error: false },
    emailRefresh: { refresh: () => undefined, refreshing: false, stalled: false },
    openPanel: () => undefined,
    panel: { kind: "inbox" },
    revision: 0,
    actions: { create: [] },
  } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(React.createElement(I18nextProvider, { i18n }, React.createElement(BusinessConsentTestProvider, { accepted: true }, React.createElement(BusinessContext.Provider, { value }, node(React))))); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  return { act, root, host };
}

describe("a receipt saved without a read never looks stuck", () => {
  test("the Bandeja row reads Guardado, sin leer; the full sentence waits in the record", async () => {
    const { default: BusinessInboxPanel } = await import("@/components/business-app/BusinessInboxPanel");
    const page = await mount((React) => React.createElement(BusinessInboxPanel), [receipt({})]);
    const state = page.host.querySelector('[data-testid="bandeja-row-state"]')?.textContent ?? "";
    assert.match(state, /^Guardado, sin leer · /);
    assert.ok(!page.host.textContent?.includes(HINT));
    assert.ok(!page.host.textContent?.includes("sin preparar"));
    await page.act(async () => page.root.unmount());
  });

  test("a receipt being read keeps its own words on the row", async () => {
    const { default: BusinessInboxPanel } = await import("@/components/business-app/BusinessInboxPanel");
    const reading = await mount((React) => React.createElement(BusinessInboxPanel), [receipt({ status: "queued", read_pending: true })]);
    await reading.act(async () => reading.host.querySelector<HTMLButtonElement>('[data-segment="all"]')!.click());
    assert.match(reading.host.querySelector('[data-testid="bandeja-row-state"]')?.textContent ?? "", /^Leyendo… · /);
    assert.ok(!reading.host.textContent?.includes("Guardado, sin leer"));
    await reading.act(async () => reading.root.unmount());
  });

  test("an email opened from the Historial says the same under the captured attachment whose receipt is still unread", async () => {
    const { EmailHistory } = await import("@/components/business-app/BusinessEmailDeliveries");
    const page = await mount((React) => React.createElement(EmailHistory), [receipt({})]);
    const row = page.host.querySelector('[data-testid="email-delivery-row"]') as HTMLButtonElement;
    await page.act(async () => { row.click(); });
    await page.act(async () => { await Promise.resolve(); await Promise.resolve(); });
    const detail = document.body.querySelector('[data-testid="email-detail"]');
    assert.equal(detail?.querySelector('[data-testid="email-part-saved-unread"]')?.textContent, HINT);
    assert.ok([...(detail?.querySelectorAll("button") ?? [])].some((b) => b.textContent === "Abrir recibo"));
    await page.act(async () => page.root.unmount());
    // Once the receipt was read, the line is gone.
    const read = await mount((React) => React.createElement(EmailHistory), [receipt({ status: "review_ready" })]);
    const row2 = read.host.querySelector('[data-testid="email-delivery-row"]') as HTMLButtonElement;
    await read.act(async () => { row2.click(); });
    await read.act(async () => { await Promise.resolve(); await Promise.resolve(); });
    assert.ok(document.body.querySelector('[data-testid="email-detail"]'), "the email opened");
    assert.equal(document.body.querySelector('[data-testid="email-part-saved-unread"]'), null);
    await read.act(async () => read.root.unmount());
  });
});
