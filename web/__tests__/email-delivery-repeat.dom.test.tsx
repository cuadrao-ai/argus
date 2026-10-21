import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { BusinessEmailDelivery } from "@/lib/business-email";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const delivery = (id: string, repeat: string | null, upload = false): BusinessEmailDelivery => ({
  id, state: "captured", received_at: "2026-10-13T17:14:00Z", updated_at: "2026-10-13T17:14:00Z", original_document_id: null, retryable: false, subject: "Factura 0041", sender: "ventas@ferreteria.example", sent_at: null, error_code: null,
  parts: [{ id: "1.2", filename: "recibo-prueba-ferreteria.pdf", media_type: "application/pdf", state: "captured", document_id: "rcpt-1", error_code: null, repeat_of_delivery_id: repeat, repeat_of_upload: upload }],
});

describe("a repeated email attachment in the email Historial", () => {
  test("the second email says the file was already received and still opens the one receipt", async () => {
    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const i18next = (await import("i18next")).default;
    const { I18nextProvider } = await import("react-i18next");
    const spanish = (await import("@/public/locales/es-419/common.json")).default;
    const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
    const { EmailHistory } = await import("@/components/business-app/BusinessEmailDeliveries");
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
    const opened: unknown[] = [];
    const value = {
      // The email rows read the Inbox's receipts to say when a saved part is still unread.
      records: { inbox: null, notes: null, notesError: false, notesTruncated: false, emails: [delivery("d2", "d1"), delivery("d1", null)], emailsError: false, workspace: null, overview: null, error: false },
      emailRefresh: { refresh: () => undefined, refreshing: false, stalled: false },
      source: { emailDelivery: async (id: string) => ({ ...delivery(id, null), text_body: "Adjunto" }) },
      openPanel: (panel: unknown) => opened.push(panel),
      revision: 0,
    } as unknown as BusinessContextValue;
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}><EmailHistory /></BusinessContext.Provider></I18nextProvider>); });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    const rows = host.querySelectorAll<HTMLButtonElement>('[data-testid="email-delivery-row"]');
    assert.equal(rows.length, 2);
    const detail = () => document.body.querySelector('[data-testid="email-detail"]');
    await act(async () => { rows[0].click(); });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    assert.equal(detail()?.querySelectorAll('[data-testid="email-part-repeat"]').length, 1);
    assert.ok(detail()?.textContent?.includes("Ya recibiste este archivo"));
    const open = [...(detail()?.querySelectorAll("button") ?? [])].find((b) => b.textContent === "Abrir recibo") as HTMLButtonElement;
    await act(async () => { open.click(); });
    assert.deepEqual(opened, [{ kind: "receipt", receiptId: "rcpt-1" }]);
    assert.equal(detail(), null, "Abrir recibo puts the email away, so the receipt is the one thing open");
    await act(async () => { rows[0].click(); });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    const back = document.body.querySelector<HTMLButtonElement>('[data-testid="side-drawer"] button[aria-label="Volver"]');
    assert.ok(back, "the opened email offers a way back to the list");
    await act(async () => { back.click(); });
    assert.equal(detail(), null, "back returns to the list");
    await act(async () => { rows[1].click(); });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    // One email opens at a time: with the first email open, no repeat mark is on the page.
    assert.equal(document.body.querySelectorAll('[data-testid="email-part-repeat"]').length, 0, "the first email carries no repeat mark");
    assert.ok(detail()?.textContent?.includes("recibo-prueba-ferreteria.pdf"));
    await act(async () => root.unmount());
  });
});

describe("an email opened as a record from a receipt's first email", () => {
  test("the named email shows, and a file first saved on the web reads as already saved", async () => {
    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const i18next = (await import("i18next")).default;
    const { I18nextProvider } = await import("react-i18next");
    const spanish = (await import("@/public/locales/es-419/common.json")).default;
    const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
    const { EmailRecord } = await import("@/components/business-app/BusinessEmailDeliveries");
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
    const value = {
      records: { inbox: null, notes: null, notesError: false, notesTruncated: false, emails: [delivery("d1", null, true)], emailsError: false, workspace: null, overview: null, error: false },
      emailRefresh: { refresh: () => undefined, refreshing: false, stalled: false },
      source: { emailDelivery: async (id: string) => ({ ...delivery(id, null, true), text_body: "Adjunto" }) },
      openPanel: () => undefined,
      revision: 0,
    } as unknown as BusinessContextValue;
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}><EmailRecord emailId="d1" /></BusinessContext.Provider></I18nextProvider>); });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    const detail = document.body.querySelector('[data-testid="email-detail"]');
    assert.ok(detail, "the named email opens");
    assert.equal(host.querySelector('[data-testid="email-record"] h2')?.textContent, "Correo de ventas@ferreteria.example");
    assert.ok(detail.textContent?.includes("Ya habías guardado este archivo"));
    await act(async () => root.unmount());
  });
});


test("opened capped mail does not fetch an unread body or offer an immediate retry", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { EmailDeliveryDetail } = await import("@/components/business-app/BusinessEmailDeliveries");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  let bodyRequests = 0;
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const base = { ...delivery("waiting", null), state: "received", parts: [], original_document_id: null, retryable: false,
    waiting: { reason: "daily_budget", retry_at: "2026-10-15T00:00:00Z" } } satisfies BusinessEmailDelivery;
  for (const code of ["email_daily_message_budget", "email_daily_byte_budget"]) {
    const item = { ...base, error_code: code };
    await act(async () => root.render(<I18nextProvider i18n={i18n}><EmailDeliveryDetail delivery={item} loadDetail={async () => { bodyRequests++; return { ...item, text_body: null }; }} openReceipt={() => undefined} retryDelivery={async () => ({ id: item.id })} /></I18nextProvider>));
    assert.equal(bodyRequests, 0);
    assert.ok(host.textContent?.includes("En espera hasta mañana"));
    assert.ok(host.textContent?.includes("Se procesará automáticamente"));
    assert.ok(!host.textContent?.includes(spanish.business.email.no_body));
    assert.equal(host.querySelector('[role="alert"]'), null);
    assert.equal([...host.querySelectorAll("button")].some((b) => b.textContent === spanish.business.email.retry), false);
  }
  await act(async () => root.unmount());
  host.remove();
});
