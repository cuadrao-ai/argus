import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReactNode } from "react";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { ReceiptSummary } from "@/lib/business-api";
import { useReceiptStateWord } from "@/components/business-app/receipt-state-word";

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

const WORDS = {
  ready: "Listo para revisar",
  reading: "Leyendo…",
  saved: "Guardado, sin leer",
  confirmed: "Aprobado",
} as const;

const STATES = [
  { id: "ready", merchant: "Ferretería Lista", status: "review_ready" },
  { id: "reading", merchant: "Colmado Leyendo", status: "queued", activity: { state: "reading", unread: false, completion_cursor: null }, bandeja: { por_revisar: true, con_problema: false, leyendo: true } },
  { id: "saved", merchant: "Papelería Guardada", status: "saved", activity: { state: "saved_unread", unread: true, completion_cursor: null } },
  { id: "confirmed", merchant: "Hosting Aprobado", status: "confirmed", activity: { state: "inactive", unread: false, completion_cursor: null } },
] as const;

function StateWords({ receipts }: { receipts: ReceiptSummary[] }) {
  const stateWord = useReceiptStateWord();
  return (
    <ul data-testid="hook-words">
      {receipts.map((item) => <li key={item.id} data-receipt={item.id}>{stateWord(item)}</li>)}
    </ul>
  );
}

function tag(host: HTMLElement, merchant: string): HTMLElement {
  const card = host.querySelector('[data-testid="home-needs-attention"]');
  const button = [...(card?.querySelectorAll("button") ?? [])].find((item) => item.textContent?.includes(merchant));
  const mark = [...(button?.querySelectorAll("span") ?? [])].find((span) => span.className.includes("rounded-mark") && span.className.includes("font-medium"));
  assert.ok(mark, merchant);
  return mark;
}

async function mount(inbox: ReceiptSummary[], extra?: ReactNode, capabilities: string[] = ["read"]) {
  const { act, createElement } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { HomeWork } = await import("@/components/business-app/inicio/HomeOverviewDraft");
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
    root.render(createElement(I18nextProvider, { i18n }, createElement(BusinessContext.Provider, { value }, createElement(HomeWork), extra ?? null)));
  });
  return {
    host,
    unmount: () => act(async () => root.unmount()),
  };
}

describe("Inicio names a receipt with the Bandeja's word", () => {
  test("ready, reading, saved-unread and confirmed rows show the shared state word", async () => {
    const inbox = STATES.map((item) => receipt(item));
    const page = await mount(inbox, <StateWords receipts={inbox} />);
    try {
      for (const item of STATES) {
        const shown = tag(page.host, item.merchant).textContent;
        const shared = page.host.querySelector(`[data-receipt="${item.id}"]`)?.textContent;
        assert.equal(shown, WORDS[item.id]);
        assert.equal(shown, shared, item.id);
        assert.match(tag(page.host, item.merchant).className, /bg-black\/5/);
        assert.equal(tag(page.host, item.merchant).className.includes("bg-[#f6dfe0]"), false);
      }
    } finally {
      await page.unmount();
    }
  });

  test("the card lists everything waiting in the Bandeja, Listos and still-reading rows included, problems first", async () => {
    const listo = receipt({ id: "listo", merchant: "Suplidora Lista", bandeja_group: { group: "listo", reason: null, draft_id: "draft", version: 1 } });
    const waiting = receipt({ id: "waiting", merchant: "Taller Sin NCF" });
    const reading = receipt({ id: "reading", merchant: "Colmado Leyendo", status: "queued", bandeja: { por_revisar: false, con_problema: false, leyendo: true }, bandeja_group: { group: "reading", reason: "reading", draft_id: null, version: null } });
    const problem = receipt({ id: "problem", merchant: "Recibo Borroso", filename: "borroso.jpg", status: "needs_attention", attention: "unreadable", received_at: "2026-10-01T10:00:00Z", bandeja: { por_revisar: false, con_problema: true, leyendo: false } });
    const page = await mount([listo, waiting, reading, problem]);
    try {
      const section = page.host.querySelector('[data-testid="home-needs-attention"]')!;
      const titles = [...section.querySelectorAll("li button")].map((item) => item.textContent ?? "");
      assert.equal(titles.length, 4);
      assert.match(titles[0], /borroso\.jpg/, "a problem leads, even the oldest; an unreadable receipt is named by its file, as the Bandeja names it");
      for (const merchant of ["Suplidora Lista", "Taller Sin NCF", "Colmado Leyendo"]) assert.ok(titles.some((title) => title.includes(merchant)), merchant);
    } finally {
      await page.unmount();
    }
  });

  test("a problem row keeps the red attention word, including when attention is absent", async () => {
    const named = receipt({ id: "problem", merchant: "Recibo Borroso", filename: "borroso.jpg", status: "needs_attention", attention: "unreadable", bandeja: { por_revisar: false, con_problema: true, leyendo: false } });
    const bare = receipt({ id: "problem-bare", merchant: "Recibo Sin Motivo", status: "needs_attention", attention: null, bandeja: { por_revisar: false, con_problema: true, leyendo: false } });
    const page = await mount([named, bare]);
    try {
      assert.equal(tag(page.host, "borroso.jpg").textContent, "No se pudo leer");
      assert.match(tag(page.host, "borroso.jpg").className, /bg-\[#f6dfe0\]/);
      assert.equal(tag(page.host, bare.merchant!).textContent, "Necesita atención");
      assert.match(tag(page.host, bare.merchant!).className, /bg-\[#f6dfe0\]/);
    } finally {
      await page.unmount();
    }
  });

  test("Resolver and Revisar show only for someone who may prepare; a read-only person sees the rows without a verb", async () => {
    const problem = receipt({ id: "problem", merchant: "Recibo Sin Motivo", status: "needs_attention", bandeja: { por_revisar: false, con_problema: true, leyendo: false } });
    const ready = receipt({ id: "ready", merchant: "Ferretería Lista", status: "review_ready" });
    const reader = await mount([problem, ready]);
    try {
      assert.doesNotMatch(reader.host.querySelector('[data-testid="home-needs-attention"]')?.textContent ?? "", /Resolver|Revisar/);
    } finally { await reader.unmount(); }
    const preparer = await mount([problem, ready], undefined, ["read", "prepare"]);
    try {
      const text = preparer.host.querySelector('[data-testid="home-needs-attention"]')?.textContent ?? "";
      assert.match(text, /Resolver/);
      assert.match(text, /Revisar/);
    } finally { await preparer.unmount(); }
  });
});
