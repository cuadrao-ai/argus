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

describe("a repeated email attachment in Correos recibidos", () => {
  test("the second email says the file was already received and still opens the one receipt", async () => {
    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const i18next = (await import("i18next")).default;
    const { I18nextProvider } = await import("react-i18next");
    const spanish = (await import("@/public/locales/es-419/common.json")).default;
    const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
    const { default: BusinessEmailDeliveries } = await import("@/components/business-app/BusinessEmailDeliveries");
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
    const opened: unknown[] = [];
    const value = {
      // The email rows read the Inbox's receipts to say when a saved part is still unread.
      records: { inbox: null, notes: null, notesError: false, notesTruncated: false, workspace: null, overview: null, error: false },
      source: { emailIntake: async () => ({ enabled: true, receiving_address: "recibos-ab12@example.test" }), emailDeliveries: async () => [delivery("d2", "d1"), delivery("d1", null)], emailDelivery: async (id: string) => ({ ...delivery(id, null), text_body: "Adjunto" }) },
      openPanel: (panel: unknown) => opened.push(panel),
      revision: 0,
    } as unknown as BusinessContextValue;
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}><BusinessEmailDeliveries /></BusinessContext.Provider></I18nextProvider>); });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    const rows = host.querySelectorAll("li");
    assert.ok(rows.length >= 2);
    const expanders = host.querySelectorAll('button[aria-expanded]');
    await act(async () => { (expanders[0] as HTMLButtonElement).click(); });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    assert.equal(host.querySelectorAll('[data-testid="email-part-repeat"]').length, 1);
    assert.ok(host.textContent?.includes("Ya recibiste este archivo"));
    const open = [...host.querySelectorAll("button")].find((b) => b.textContent === "Abrir recibo") as HTMLButtonElement;
    await act(async () => { open.click(); });
    assert.deepEqual(opened, [{ kind: "receipt", receiptId: "rcpt-1" }]);
    await act(async () => { (expanders[1] as HTMLButtonElement).click(); });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    // One email expands at a time: with the first email open, no repeat mark is on the page.
    assert.equal(host.querySelectorAll('[data-testid="email-part-repeat"]').length, 0, "the first email carries no repeat mark");
    assert.ok(host.textContent?.includes("recibo-prueba-ferreteria.pdf"));
    await act(async () => root.unmount());
  });
});

describe("the inbox opened from a receipt's first email", () => {
  test("the named email starts expanded, and a file first saved on the web reads as already saved", async () => {
    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const i18next = (await import("i18next")).default;
    const { I18nextProvider } = await import("react-i18next");
    const spanish = (await import("@/public/locales/es-419/common.json")).default;
    const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
    const { default: BusinessEmailDeliveries } = await import("@/components/business-app/BusinessEmailDeliveries");
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
    const value = {
      // The email rows read the Inbox's receipts to say when a saved part is still unread.
      records: { inbox: null, notes: null, notesError: false, notesTruncated: false, workspace: null, overview: null, error: false },
      source: { emailIntake: async () => ({ enabled: true, receiving_address: "recibos-ab12@example.test" }), emailDeliveries: async () => [delivery("d1", null, true)], emailDelivery: async (id: string) => ({ ...delivery(id, null, true), text_body: "Adjunto" }) },
      openPanel: () => undefined,
      revision: 0,
    } as unknown as BusinessContextValue;
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}><BusinessEmailDeliveries openEmailId="d1" /></BusinessContext.Provider></I18nextProvider>); });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    assert.equal(host.querySelector('button[aria-expanded]')?.getAttribute("aria-expanded"), "true");
    assert.ok(host.textContent?.includes("Ya habías guardado este archivo"));
    await act(async () => root.unmount());
  });
});
