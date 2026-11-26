import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { BandejaLabel, ReceiptSummary } from "@/lib/business-api";
import type { BusinessEmailDelivery } from "@/lib/business-email";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

function receipt(merchant: string, label: BandejaLabel | null, day = 13): ReceiptSummary {
  return {
    id: merchant,
    merchant,
    channel: "web",
    title: merchant, filename: "recibo.pdf",
    media_type: "application/pdf",
    size_bytes: 70,
    received_at: `2026-10-${day}T17:14:00Z`,
    status: "needs_attention",
    error_code: null,
    attention: "check_details",
    preparable: false,
    enterable: false,
    bandeja: { por_revisar: true, con_problema: true, leyendo: false },
    bandeja_group: { group: "attention", reason: "missing_ncf", label, draft_id: null, version: null },
    expense_id: null,
    occurred_on: null,
    amount: "120.55",
    currency: "DOP",
    category_id: null,
    account_id: null,
  };
}

const rows = (host: HTMLElement) => [...host.querySelectorAll('[data-testid="home-attention-rows"] > li')];
function rowFor(host: HTMLElement, title: string): Element {
  const row = rows(host).find((item) => item.querySelector('[data-testid="home-attention-title"]')?.textContent === title);
  assert.ok(row, title);
  return row;
}
const pill = (row: Element) => row.querySelector('[data-testid="status-pill"]');
const verb = (row: Element) => row.querySelector('[data-testid="home-attention-verb"]')?.textContent ?? null;

async function mount(inbox: ReceiptSummary[], capabilities: string[] = ["read", "prepare"], language: "es-419" | "en" = "es-419", emails: BusinessEmailDelivery[] = []) {
  const { act, createElement } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const english = (await import("@/public/locales/en/common.json")).default;
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { HomeAttention } = await import("@/components/business-app/inicio/HomeAttention");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: language, resources: { "es-419": { translation: spanish }, en: { translation: english } }, interpolation: { escapeValue: false } });
  const opened: unknown[] = [];
  const value = {
    source: { mode: "fixture" },
    // The server's one Bandeja count: every row waiting, as the sidebar shows it.
    records: { inbox, notes: [], emails, error: false, receiptActivity: { pending_review_count: inbox.length + emails.length } },
    openPanel: (panel: unknown) => { opened.push(panel); },
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
    opened,
    act,
    unmount: async () => { await act(async () => root.unmount()); host.remove(); },
  };
}

const LABELS = [
  ["cant_read", "No se pudo leer", "attention", "Resolver"],
  ["needs_attention", "Necesita atención", "caution", "Resolver"],
  ["ready", "Listo para aceptar", "toAccept", "Revisar"],
  ["reading", "Leyendo…", "neutral", null],
  ["accepted", "Aceptado", "approved", null],
  [null, null, null, null],
] as const;

describe("Inicio names a row with the Bandeja's label", () => {
  test.each([["es-419", "Pendientes"], ["en", "Pending"]] as const)("the heading in %s is %s", async (language, heading) => {
    const page = await mount([receipt("Ferretería", "ready")], ["read"], language);
    try {
      assert.equal(page.host.querySelector('[data-testid="home-attention"] h2')?.textContent, heading);
    } finally { await page.unmount(); }
  });

  test.each(LABELS)("label %s gives the Bandeja's words and tone", async (label, words, tone) => {
    const page = await mount([receipt("Ferretería", label)]);
    try {
      const row = rowFor(page.host, "Ferretería");
      const arrival = row.querySelector('[data-testid="home-attention-time"]');
      assert.ok(arrival);
      assert.equal(arrival.previousElementSibling?.textContent ?? null, words);
      assert.equal(pill(row)?.className ?? null, tone ? `workflow ${tone}` : null);
      assert.equal(pill(row)?.getAttribute("data-label") ?? null, label);
    } finally { await page.unmount(); }
  });

  test.each(LABELS)("label %s controls the verb for a preparer", async (label, _words, _tone, action) => {
    const item = receipt("Ferretería", label);
    if (label === "cant_read" || label === "needs_attention") {
      item.bandeja_group = { group: "listo", reason: null, label, draft_id: "draft", version: 1 };
    }
    const page = await mount([item]);
    try {
      assert.equal(verb(rowFor(page.host, "Ferretería")), action);
    } finally { await page.unmount(); }
  });

  test("a problem row leaves out its reason, dot and amount", async () => {
    const page = await mount([receipt("Ferretería", "needs_attention")]);
    try {
      const row = rowFor(page.host, "Ferretería");
      assert.doesNotMatch(row.textContent ?? "", /Falta el NCF|120[.,]55|RD\$/);
      assert.equal(pill(row)?.childElementCount, 0);
    } finally { await page.unmount(); }
  });

  test("an email shows the Bandeja label without its delivery reason", async () => {
    const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
    const emails = await createFixtureBusinessDataSource().emailDeliveries();
    const email = emails.find((delivery) => delivery.id === "email-boletin");
    assert.equal(email?.no_receipt_reason, "unsupported_media_type");
    assert.ok(email);
    const page = await mount([], ["read", "prepare"], "es-419", [email]);
    try {
      const row = rowFor(page.host, "Boletín semanal");
      assert.doesNotMatch(row.textContent ?? "", /Este tipo de archivo no se puede guardar como recibo/);
      assert.equal(pill(row)?.textContent, "Necesita atención");
      assert.equal(verb(row), "Resolver");
      const button = row.querySelector("button");
      assert.ok(button);
      await page.act(async () => button.click());
      assert.deepEqual(page.opened, [{ kind: "email", emailId: email.id }]);
    } finally { await page.unmount(); }
  });

  test("only problem labels lead, with each group keeping the Bandeja's order", async () => {
    const pending = [
      receipt("Ferretería", "ready", 16),
      receipt("Colmado", null, 15),
      receipt("Panadería", "cant_read", 14),
      receipt("Farmacia", "reading", 13),
      receipt("Papelería", "needs_attention", 12),
    ];
    const page = await mount(pending);
    try {
      assert.deepEqual(rows(page.host).map((row) => row.querySelector('[data-testid="home-attention-title"]')?.textContent),
        ["Panadería", "Papelería", "Ferretería", "Colmado", "Farmacia"]);
    } finally { await page.unmount(); }
  });

  test("read-only users see the same pills and can open rows without action verbs", async () => {
    const page = await mount([receipt("Colmado", "needs_attention"), receipt("Ferretería", "ready")], ["read"]);
    try {
      for (const [title, words] of [["Colmado", "Necesita atención"], ["Ferretería", "Listo para aceptar"]]) {
        const row = rowFor(page.host, title);
        assert.equal(verb(row), null);
        const button = row.querySelector("button");
        assert.ok(button);
        await page.act(async () => button.click());
        const arrival = row.querySelector('[data-testid="home-attention-time"]');
        assert.equal(arrival?.previousElementSibling?.textContent, words);
      }
      assert.deepEqual(page.opened, [
        { kind: "receipt", receiptId: "Colmado", list: "inbox" },
        { kind: "receipt", receiptId: "Ferretería", list: "inbox" },
      ]);
    } finally { await page.unmount(); }
  });
});
