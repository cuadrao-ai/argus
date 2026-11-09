import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { ReceiptSummary } from "@/lib/business-api";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const receipt = (over: Partial<ReceiptSummary> & Pick<ReceiptSummary, "id" | "merchant" | "status">): ReceiptSummary =>
  ({
    channel: "web",
    filename: "recibo.pdf",
    source_text: null,
    media_type: "application/pdf",
    size_bytes: 70,
    received_at: "2026-10-13T17:14:00Z",
    error_code: null,
    attention: null,
    duplicate_of: null,
    replayed: false,
    preparable: false,
    enterable: false,
    activity: { state: "ready", unread: false, completion_cursor: null },
    bandeja: { por_revisar: true, con_problema: false, leyendo: false },
    bandeja_group: { group: "attention", reason: "missing_ncf", draft_id: null, version: null },
    expense_id: null,
    occurred_on: null,
    amount: null,
    currency: null,
    category_id: null,
    account_id: null,
    email_delivery_ids: [],
    email_original: false,
    missing_fields: [],
    version: 1,
    draft_id: null,
    ...over,
  }) as unknown as ReceiptSummary;

function tag(host: HTMLElement, title: string): HTMLElement {
  const card = host.querySelector('[data-testid="home-attention"]');
  const button = [...(card?.querySelectorAll("button") ?? [])].find((item) => item.textContent?.includes(title));
  const mark = [...(button?.querySelectorAll("span") ?? [])].find((span) => span.className.includes("rounded-mark") && span.className.includes("font-medium"));
  assert.ok(mark, title);
  return mark;
}

async function mount(inbox: ReceiptSummary[], capabilities: string[] = ["read"]) {
  const { act, createElement } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { HomeAttention } = await import("@/components/business-app/inicio/HomeAttention");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const value = {
    source: { mode: "fixture" },
    // The server's one Bandeja count: every row waiting, as the sidebar shows it.
    records: { inbox, notes: [], emails: [], error: false, receiptActivity: { pending_review_count: inbox.length } },
    openPanel: () => undefined,
    reload: () => undefined,
    chosen: { space_id: "local-business-inicio-state", name: "Negocio de prueba", grant_id: "g", role: "owner", capabilities },
    userId: null,
    panel: { kind: "overview" },
  } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(createElement(I18nextProvider, { i18n }, createElement(BusinessContext.Provider, { value }, createElement(HomeAttention, { firstDay: false }))));
  });
  return {
    host,
    unmount: () => act(async () => root.unmount()),
  };
}

describe("Inicio names a row with the Bandeja's word", () => {
  test("a ready or still-reading row is neutral; a problem is red, with the Bandeja's reason and its dot", async () => {
    const listo = receipt({ id: "listo", merchant: "Suplidora Lista", status: "review_ready", bandeja_group: { group: "listo", reason: null, draft_id: "draft", version: 1 } });
    const reading = receipt({ id: "reading", merchant: "Colmado Leyendo", status: "queued", bandeja_group: { group: "reading", reason: "reading", draft_id: null, version: null } });
    const missing = receipt({ id: "missing", merchant: "Taller Sin NCF" });
    const unreadable = receipt({ id: "unreadable", merchant: null, filename: "borroso.jpg", status: "needs_attention", attention: "unreadable", bandeja_group: { group: "attention", reason: "unreadable", draft_id: null, version: null } });
    const bare = receipt({ id: "bare", merchant: "Recibo Sin Motivo", status: "needs_attention", bandeja_group: { group: "attention", reason: null, draft_id: null, version: null } });
    const page = await mount([listo, reading, missing, unreadable, bare]);
    try {
      for (const [title, word] of [["Suplidora Lista", "Listo para revisar"], ["Colmado Leyendo", "Leyendo…"]]) {
        assert.equal(tag(page.host, title).textContent, word);
        assert.match(tag(page.host, title).className, /bg-black\/5/);
      }
      for (const [title, word] of [["Taller Sin NCF", "Falta el NCF"], ["borroso.jpg", "No se pudo leer"], ["Recibo Sin Motivo", "Necesita atención"]]) {
        assert.equal(tag(page.host, title).textContent, word, title);
        assert.match(tag(page.host, title).className, /bg-\[#f6dfe0\]/);
      }
    } finally {
      await page.unmount();
    }
  });

  test("the card lists everything waiting in the Bandeja, problems first", async () => {
    const listo = receipt({ id: "listo", merchant: "Suplidora Lista", received_at: "2026-10-13T18:00:00Z", bandeja_group: { group: "listo", reason: null, draft_id: "draft", version: 1 } });
    const reading = receipt({ id: "reading", merchant: "Colmado Leyendo", status: "queued", bandeja_group: { group: "reading", reason: "reading", draft_id: null, version: null } });
    const problem = receipt({ id: "problem", merchant: "Recibo Borroso", filename: "borroso.jpg", status: "needs_attention", attention: "unreadable", received_at: "2026-10-01T10:00:00Z", bandeja_group: { group: "attention", reason: "unreadable", draft_id: null, version: null } });
    const page = await mount([listo, reading, problem]);
    try {
      const titles = [...page.host.querySelectorAll('[data-testid="home-attention"] li button')].map((item) => item.textContent ?? "");
      assert.equal(titles.length, 3);
      assert.match(titles[0], /borroso\.jpg/, "a problem leads, even the oldest; an unreadable receipt is named by its file, as the Bandeja names it");
      for (const merchant of ["Suplidora Lista", "Colmado Leyendo"]) assert.ok(titles.some((title) => title.includes(merchant)), merchant);
    } finally {
      await page.unmount();
    }
  });

  test("Resolver and Revisar show only for someone who may prepare; a read-only person sees the rows without a verb", async () => {
    const problem = receipt({ id: "problem", merchant: "Recibo Sin Motivo", status: "needs_attention" });
    const ready = receipt({ id: "ready", merchant: "Ferretería Lista", status: "review_ready", bandeja_group: { group: "listo", reason: null, draft_id: "d", version: 1 } });
    const reader = await mount([problem, ready]);
    try {
      assert.doesNotMatch(reader.host.querySelector('[data-testid="home-attention"]')?.textContent ?? "", /Resolver|Revisar/);
    } finally { await reader.unmount(); }
    const preparer = await mount([problem, ready], ["read", "prepare"]);
    try {
      const text = preparer.host.querySelector('[data-testid="home-attention"]')?.textContent ?? "";
      assert.match(text, /Resolver/);
      assert.match(text, /Revisar/);
    } finally { await preparer.unmount(); }
  });
});
