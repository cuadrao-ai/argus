import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessOverview, ReceiptSummary } from "@/lib/business-api";
import type { BusinessDossier } from "@/lib/business-dossier";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";

// A real DOM: the Personal control sits beside the row's button, the toast
// offers the way back, and the 606 answer belongs to the accountant alone.
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const receipt = (over: Partial<ReceiptSummary> = {}): ReceiptSummary =>
  ({ id: "rcpt-1", channel: "web", filename: "recibo.png", source_text: null, media_type: "image/png", size_bytes: 10, received_at: "2026-10-12T14:00:00Z", status: "review_ready", error_code: null, attention: null, preparable: false, enterable: false, expense_id: null, merchant: "Ferretería Luna", occurred_on: "2026-10-12", amount: "850.00", currency: "DOP", category_id: null, account_id: null, ...over }) as ReceiptSummary;

async function setup() {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const settle = () => act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
  return { act, root, host, settle, I18nextProvider, i18n };
}

describe("the chips", () => {
  test("a read receipt without a fiscal number says so in grey text; a personal one says Personal; a receipt not yet read says nothing", async () => {
    const env = await setup();
    const { RecordMarks } = await import("@/components/business-app/business-ui");
    const render = (props: Parameters<typeof RecordMarks>[0]) => env.act(async () => { env.root.render(<env.I18nextProvider i18n={env.i18n}><RecordMarks {...props} /></env.I18nextProvider>); });
    await render({ known: true, fiscalValue: null });
    const chip = env.host.querySelector('[data-mark="no_fiscal"]')!;
    assert.equal(chip.textContent, "Sin comprobante fiscal");
    assert.ok(!/amber|red|warning|danger/.test(chip.className), "grey, never amber or red");
    await render({ known: true, fiscalValue: "ncf" });
    assert.equal(env.host.querySelector('[data-testid="record-marks"]'), null);
    await render({ known: false, fiscalValue: null });
    assert.equal(env.host.querySelector('[data-testid="record-marks"]'), null);
    await render({ known: true, fiscalValue: "ncf", personal: true });
    assert.equal(env.host.querySelector('[data-mark="personal"]')?.textContent, "Personal");
    assert.equal(env.host.querySelector('[data-mark="no_fiscal"]'), null);
    await env.act(async () => env.root.unmount());
  });
});

describe("the Overview's two totals", () => {
  test("Gastos reales and Con valor fiscal stand side by side with the 606 line under the second, from the server's numbers", async () => {
    const env = await setup();
    const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
    const { default: BusinessOverviewPanel } = await import("@/components/business-app/BusinessOverviewPanel");
    const overview: BusinessOverview = { from: "2026-10-01", to: "2026-10-31", today: "2026-10-13", totals: [{ currency: "DOP", amount: "5000.00", count: 3 }], fiscal_totals: [{ currency: "DOP", amount: "3500.00", count: 2 }], without_fiscal_totals: [{ currency: "DOP", amount: "1500.00", count: 1 }], needs_attention: 0, last_received_at: null, last_confirmed_at: null, outside_period_count: 0, outside_period_latest_on: null };
    const value = { records: { overview, inbox: [], notes: [], workspace: null, error: false, notesError: false, notesTruncated: false }, period: { key: "this_month", from: "2026-10-01", to: null }, setPeriod: () => undefined, openPanel: () => undefined, actions: { starterEntries: [] }, chosen: null } as unknown as BusinessContextValue;
    await env.act(async () => { env.root.render(<env.I18nextProvider i18n={env.i18n}><BusinessContext.Provider value={value}><BusinessOverviewPanel /></BusinessContext.Provider></env.I18nextProvider>); });
    const real = env.host.querySelector('[data-testid="overview-real-expenses"]')!;
    const fiscal = env.host.querySelector('[data-testid="overview-fiscal-expenses"]')!;
    assert.ok(real.textContent?.includes("Gastos reales") && real.textContent?.includes("5,000.00"));
    assert.ok(fiscal.textContent?.includes("Con valor fiscal") && fiscal.textContent?.includes("3,500.00"));
    assert.ok(env.host.querySelector('[data-testid="overview-without-fiscal"]')?.textContent?.includes("Sin comprobante fiscal: RD$ 1,500.00 no entra al 606") || env.host.querySelector('[data-testid="overview-without-fiscal"]')?.textContent?.includes("no entra al 606"));
    assert.equal(real.className, fiscal.className, "equal weight");
    await env.act(async () => env.root.unmount());
  });
});

describe("the Personal control in the Bandeja", () => {
  async function mountRow(item: ReceiptSummary, marks: ((r: ReceiptSummary) => void) | undefined) {
    const env = await setup();
    const { ReceiptRow } = await import("@/components/business-app/BusinessInboxPanel");
    await env.act(async () => { env.root.render(<env.I18nextProvider i18n={env.i18n}><ul><ReceiptRow receipt={item} onOpen={() => undefined} onMark={marks} /></ul></env.I18nextProvider>); });
    return env;
  }

  test("the owner gets a sibling button next to the row, pressed when personal; a grantee gets the chip only", async () => {
    const marked: string[] = [];
    const owner = await mountRow(receipt({ personal_editable: true, fiscal_value: null }), (r) => marked.push(r.id));
    const button = owner.host.querySelector('[data-testid="mark-personal-rcpt-1"]') as HTMLButtonElement;
    assert.ok(button, "a Personal control");
    assert.equal(button.closest("button"), button, "not nested in the row's button");
    assert.equal(button.getAttribute("aria-pressed"), "false");
    assert.equal(button.getAttribute("aria-label"), "Marcar como personal");
    assert.ok(button.className.includes("min-h-11"));
    await owner.act(async () => { button.click(); });
    assert.deepEqual(marked, ["rcpt-1"]);
    assert.ok(owner.host.querySelector('[data-mark="no_fiscal"]'), "the grey chip on the row");
    await owner.act(async () => owner.root.unmount());
    const grantee = await mountRow(receipt({ personal: true, fiscal_value: "ncf" }), () => undefined);
    assert.equal(grantee.host.querySelector('[data-testid="mark-personal-rcpt-1"]'), null);
    assert.equal(grantee.host.querySelector('[data-mark="personal"]')?.textContent, "Personal");
    await grantee.act(async () => grantee.root.unmount());
  });
});

describe("the receipt page's marks card", () => {
  const dossier = (over: Partial<BusinessDossier> = {}, personal = false, ncf = true, answer: boolean | null = null): BusinessDossier =>
    ({
      draft_id: "d-1",
      version: 3,
      capabilities: ["read", "prepare"],
      history: [{ version: 3, actor: { actor_id: "a", actor_kind: "member", display_name: "Lía", grant_id: "g", issuer_id: "o", issuer_display_name: "Dueño" }, before: null, after: {}, source_ids: [], created_at: "2026-10-13T10:00:00Z" }],
      facts: {
        business_share: { state: "known", value: { kind: personal ? "none" : "all" }, origin: "owner_stated", verified: true, source_ids: ["s"] },
        fiscal: ncf ? { rnc: { state: "unknown", value: null, origin: null, verified: false, source_ids: [] }, ncf: { state: "known", value: "B0100000001", origin: "extracted", verified: false, source_ids: ["s"] }, ecf: { state: "unknown", value: null, origin: null, verified: false, source_ids: [] }, itbis: { state: "unknown", value: null, origin: null, verified: false, source_ids: [] }, include_606: answer === null ? { state: "unknown", value: null, origin: null, verified: false, source_ids: [] } : { state: "known", value: answer, origin: "member_set", verified: true, source_ids: ["s"] } } : null,
      },
      ...over,
    }) as unknown as BusinessDossier;

  async function mountCard(d: BusinessDossier, role: "owner" | "accountant") {
    const env = await setup();
    const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
    const { default: ReceiptMarksCard } = await import("@/components/business-app/ReceiptMarksCard");
    const calls: string[] = [];
    const value = {
      chosen: role === "owner" ? null : { space_id: "s", name: "Colmado Peña", grant_id: "g", role: "accountant", capabilities: ["read", "prepare"], access_seen: true },
      reload: () => undefined,
      source: {
        markPersonal: async (id: string, version: number, personal: boolean) => { calls.push(`mark:${personal}:${version}`); return dossier({}, personal, true, null); },
        decideFiscalInclusion: async (id: string, version: number, include: boolean) => { calls.push(`606:${include}:${version}`); return dossier({}, true, true, include); },
      },
    } as unknown as BusinessContextValue;
    const changed: BusinessDossier[] = [];
    await env.act(async () => { env.root.render(<env.I18nextProvider i18n={env.i18n}><BusinessContext.Provider value={value}><ReceiptMarksCard dossier={d} onChanged={(next) => changed.push(next)} /></BusinessContext.Provider></env.I18nextProvider>); });
    return { ...env, calls, changed };
  }

  test("the owner marks and unmarks; the 606 is read-only for the owner: pending, included or not", async () => {
    const page = await mountCard(dossier({}, false, false), "owner");
    const toggle = page.host.querySelector('[data-testid="receipt-mark-personal"]') as HTMLButtonElement;
    assert.equal(toggle.textContent, "Marcar como personal");
    assert.equal(page.host.querySelector('[data-testid="receipt-606"]'), null, "nothing to decide without a fiscal number");
    await page.act(async () => { toggle.click(); });
    await page.settle();
    assert.deepEqual(page.calls, ["mark:true:3"]);
    assert.equal(page.changed.length, 1);
    await page.act(async () => page.root.unmount());
    const pending = await mountCard(dossier({}, true, true, null), "owner");
    assert.equal(pending.host.querySelector('[data-testid="receipt-606-state"]')?.textContent, "Pendiente de contador");
    assert.equal(pending.host.querySelector('[data-testid="receipt-606-yes"]'), null, "the owner never answers");
    assert.equal((pending.host.querySelector('[data-testid="receipt-mark-personal"]') as HTMLButtonElement).textContent, "Ya no es personal");
    await pending.act(async () => pending.root.unmount());
    const included = await mountCard(dossier({}, true, true, true), "owner");
    assert.equal(included.host.querySelector('[data-testid="receipt-606-state"]')?.textContent, "Incluido en 606");
    await included.act(async () => included.root.unmount());
  });

  test("the accountant sees Sí and No, 44px each, only for a personal receipt with a fiscal number, and never the Personal control", async () => {
    const page = await mountCard(dossier({}, true, true, null), "accountant");
    assert.equal(page.host.querySelector('[data-testid="receipt-mark-personal"]'), null);
    assert.ok(page.host.textContent?.includes("Solo el dueño puede marcar un recibo como personal."));
    assert.ok(page.host.textContent?.includes("¿Incluir en 606?"));
    const yes = page.host.querySelector('[data-testid="receipt-606-yes"]') as HTMLButtonElement;
    const no = page.host.querySelector('[data-testid="receipt-606-no"]') as HTMLButtonElement;
    assert.equal(yes.textContent, "Sí");
    assert.equal(no.textContent, "No");
    assert.ok(yes.className.includes("min-h-11") && no.className.includes("min-h-11"));
    await page.act(async () => { no.click(); });
    await page.settle();
    assert.deepEqual(page.calls, ["606:false:3"]);
    await page.act(async () => page.root.unmount());
    const answered = await mountCard(dossier({}, true, true, false), "accountant");
    assert.equal(answered.host.querySelector('[data-testid="receipt-606-state"]')?.textContent, "Fuera del 606 por Lía");
    assert.equal(answered.host.querySelector('[data-testid="receipt-606-yes"]'), null);
    await answered.act(async () => answered.root.unmount());
    const notPersonal = await mountCard(dossier({}, false, true, null), "accountant");
    assert.equal(notPersonal.host.querySelector('[data-testid="receipt-606"]'), null);
    await notPersonal.act(async () => notPersonal.root.unmount());
  });
});
