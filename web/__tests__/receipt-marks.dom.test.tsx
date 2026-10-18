import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessOverview, ReceiptSummary } from "@/lib/business-api";
import type { BusinessDossier } from "@/lib/business-dossier";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";

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
    assert.equal(env.host.querySelector('[data-testid="personal-marked-dot"]'), null, "the owner's own mark has no dot");
    assert.equal(env.host.querySelector('[data-mark="no_fiscal"]'), null);
    await env.act(async () => env.root.unmount());
  });

  test("the owner sees a dot on the Personal chip when someone else marked it, read as Marcado por <nombre>; the accountant does not", async () => {
    const env = await setup();
    const { RecordMarks } = await import("@/components/business-app/business-ui");
    const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
    const render = (role: "owner" | "accountant") => env.act(async () => {
      const value = { chosen: role === "owner" ? { space_id: "s", name: "Mi negocio", grant_id: "own", role: "owner", capabilities: ["read", "prepare", "approve"], access_seen: true } : { space_id: "s", name: "Colmado Peña", grant_id: "g", role: "accountant", capabilities: ["read", "prepare"], access_seen: true } } as unknown as BusinessContextValue;
      env.root.render(<env.I18nextProvider i18n={env.i18n}><BusinessContext.Provider value={value}><RecordMarks known fiscalValue="ncf" personal markedBy="Marta" /></BusinessContext.Provider></env.I18nextProvider>);
    });
    await render("owner");
    const chip = env.host.querySelector('[data-mark="personal"]')!;
    assert.ok(chip.querySelector('[data-testid="personal-marked-dot"]'), "a dot on the chip");
    assert.equal(chip.querySelector('[data-testid="personal-marked-dot"]')?.getAttribute("aria-hidden"), "true", "the dot is not read twice");
    assert.equal(chip.querySelector(".sr-only")?.textContent, "Marcado por Marta");
    assert.equal(chip.getAttribute("title"), "Marcado por Marta");
    await render("accountant");
    assert.equal(env.host.querySelector('[data-testid="personal-marked-dot"]'), null);
    assert.equal(env.host.querySelector('[data-mark="personal"]')?.textContent, "Personal");
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

  test("anyone the server lets prepare gets a row menu; a read-only grant gets the chip only", async () => {
    const marked: string[] = [];
    const owner = await mountRow(receipt({ personal_editable: true, fiscal_known: true, fiscal_value: null }), (r) => marked.push(r.id));
    const trigger = owner.host.querySelector('[aria-haspopup="menu"]') as HTMLButtonElement;
    assert.ok(trigger, "a row menu");
    assert.equal(owner.host.querySelector('[role="menuitem"]'), null);
    await owner.act(async () => trigger.click());
    const button = owner.host.querySelector('[role="menuitem"]') as HTMLButtonElement;
    assert.ok(button, "a Personal control");
    assert.equal(button.closest("button"), button, "not nested in the row's button");
    assert.equal(button.textContent, "Marcar como personal");
    assert.ok(button.className.includes("min-h-11"));
    await owner.act(async () => { button.click(); });
    assert.deepEqual(marked, ["rcpt-1"]);
    assert.ok(owner.host.querySelector('[data-mark="no_fiscal"]'), "the grey chip on the row");
    await owner.act(async () => owner.root.unmount());
    const reader = await mountRow(receipt({ personal: true, fiscal_value: "ncf" }), () => undefined);
    assert.equal(reader.host.querySelector('[aria-haspopup="menu"]'), null);
    assert.equal(reader.host.querySelector('[data-mark="personal"]')?.textContent, "Personal");
    await reader.act(async () => reader.root.unmount());
  });

  test("the owner sees who marked the receipt and takes the mark back through its menu", async () => {
    const marked: ReceiptSummary[] = [];
    const owner = await mountRow(receipt({ personal: true, personal_marked_by: "Marta", personal_editable: true, fiscal_value: "ncf" }), (r) => marked.push(r));
    assert.ok(owner.host.querySelector('[data-mark="personal"] [data-testid="personal-marked-dot"]'), "the dot on the chip");
    assert.equal(owner.host.querySelector('[data-mark="personal"] .sr-only')?.textContent, "Marcado por Marta");
    const trigger = owner.host.querySelector('[aria-haspopup="menu"]') as HTMLButtonElement;
    assert.ok(trigger, "a row menu");
    assert.equal(owner.host.querySelector('[role="menuitem"]'), null);
    await owner.act(async () => trigger.click());
    const button = owner.host.querySelector('[role="menuitem"]') as HTMLButtonElement;
    assert.equal(button.textContent, "Ya no es personal");
    await owner.act(async () => { button.click(); });
    assert.equal(marked.length, 1, "one tap");
    assert.equal(marked[0].personal, true, "the unmark of the receipt as listed");
    await owner.act(async () => owner.root.unmount());
  });
});

describe("the receipt page's marks card", () => {
  const OWNER = { actor_id: "o", actor_kind: "member", display_name: "Dueño", grant_id: "own", issuer_id: "o", issuer_display_name: "Dueño" };
  const ACCOUNTANT = { actor_id: "a", actor_kind: "member", display_name: "Lía", grant_id: "g", issuer_id: "o", issuer_display_name: "Dueño" };
  const share = (kind: "all" | "none", origin: string) => ({ state: "known", value: { kind }, origin, verified: true, source_ids: ["s"] });
  const dossier = (over: Partial<BusinessDossier> = {}, personal = false, ncf = true, answer: boolean | null = null, markedBy: "owner" | "accountant" = "owner"): BusinessDossier =>
    ({
      draft_id: "d-1",
      version: 3,
      capabilities: ["read", "prepare"],
      history: [
        { version: 2, actor: markedBy === "owner" ? OWNER : ACCOUNTANT, before: { business_share: share("all", "extracted") }, after: { business_share: share(personal ? "none" : "all", markedBy === "owner" ? "owner_stated" : "member_set") }, source_ids: [], created_at: "2026-10-13T09:00:00Z" },
        { version: 3, actor: ACCOUNTANT, before: null, after: {}, source_ids: [], created_at: "2026-10-13T10:00:00Z" },
      ],
      // The marks as the server reads them: the card renders these, never its own reading of the facts.
      personal,
      personal_marked_by: personal && markedBy === "accountant" ? "Lía" : null,
      fiscal_value: ncf ? "ncf" : null,
      include_606: personal && ncf ? answer : null,
      include_606_by: personal && ncf && answer !== null ? "Lía" : null,
      fiscal_known: true,
      facts: {
        business_share: share(personal ? "none" : "all", markedBy === "owner" ? "owner_stated" : "member_set"),
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
    assert.equal(pending.host.querySelector('[data-testid="receipt-606-state"]')?.textContent, "Pendiente del contador");
    assert.equal(pending.host.querySelector('[data-testid="personal-marked-dot"]'), null, "the owner's own mark");
    assert.equal(pending.host.querySelector('[data-testid="receipt-606-yes"]'), null, "the owner never answers");
    assert.equal((pending.host.querySelector('[data-testid="receipt-mark-personal"]') as HTMLButtonElement).textContent, "Ya no es personal");
    await pending.act(async () => pending.root.unmount());
    const included = await mountCard(dossier({}, true, true, true), "owner");
    assert.equal(included.host.querySelector('[data-testid="receipt-606-state"]')?.textContent, "Incluido en 606");
    await included.act(async () => included.root.unmount());
  });

  test("the owner sees who else marked it and undoes the accountant's mark in one tap", async () => {
    const page = await mountCard(dossier({}, true, true, null, "accountant"), "owner");
    assert.equal(page.host.querySelector('[data-mark="personal"] .sr-only')?.textContent, "Marcado por Lía");
    const toggle = page.host.querySelector('[data-testid="receipt-mark-personal"]') as HTMLButtonElement;
    assert.equal(toggle.textContent, "Ya no es personal");
    await page.act(async () => { toggle.click(); });
    await page.settle();
    assert.deepEqual(page.calls, ["mark:false:3"]);
    assert.equal(page.changed.length, 1);
    await page.act(async () => page.root.unmount());
  });

  test("a read-only grant reads the mark and has no control", async () => {
    const page = await mountCard(dossier({ capabilities: ["read"] } as Partial<BusinessDossier>, true, true, null, "accountant"), "accountant");
    assert.equal(page.host.querySelector('[data-testid="receipt-mark-personal"]'), null);
    assert.equal(page.host.querySelector('[data-mark="personal"]')?.textContent, "Personal");
    assert.equal(page.host.querySelector('[data-testid="receipt-606-yes"]'), null);
    await page.act(async () => page.root.unmount());
  });

  test("the accountant with prepare marks Personal too, and sees Sí and No, 44px each, only for a personal receipt with a fiscal number", async () => {
    const page = await mountCard(dossier({}, true, true, null), "accountant");
    assert.equal((page.host.querySelector('[data-testid="receipt-mark-personal"]') as HTMLButtonElement).textContent, "Ya no es personal");
    assert.ok(!page.host.textContent?.includes("Solo el dueño"));
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

describe("the review page's fiscal details", () => {
  async function facts(fiscal: Record<string, unknown> | null, lng: "es-419" | "en" = "es-419") {
    const env = await setup();
    if (lng === "en") {
      env.i18n.addResourceBundle("en", "translation", (await import("@/public/locales/en/common.json")).default);
      await env.i18n.changeLanguage("en");
    }
    const { default: ReceiptRecordFacts } = await import("@/components/business-app/ReceiptRecordFacts");
    const unknown = { state: "unknown", value: null, origin: null, verified: false, source_ids: [] };
    const ncf = fiscal && (fiscal as { ncf?: { state?: string } }).ncf?.state === "known";
    const d = { draft_id: "d-1", version: 1, capabilities: ["read"], blockers: [], questions: [], history: [], fiscal_known: true, fiscal_value: ncf ? "ncf" : null, facts: { kind: unknown, amount: unknown, currency: unknown, occurred_on: unknown, counterparty: unknown, funding: unknown, business_share: unknown, receipt_state: unknown, category_id: unknown, fiscal } } as unknown as BusinessDossier;
    await env.act(async () => { env.root.render(<env.I18nextProvider i18n={env.i18n}><ReceiptRecordFacts dossier={d} accounts={[]} /></env.I18nextProvider>); });
    return env;
  }
  const unknown = { state: "unknown", value: null, origin: null, verified: false, source_ids: [] };

  test("a record without an NCF or an e-CF reads Sin comprobante fiscal in its fiscal row, never No registrado", async () => {
    for (const fiscal of [null, { rnc: unknown, ncf: unknown, ecf: unknown, itbis: unknown }]) {
      const env = await facts(fiscal);
      const section = env.host.querySelector('[data-testid="receipt-fiscal-facts"]')!;
      assert.ok(section, "the fiscal details are there");
      const row = section.querySelector('[data-fact="fiscal_number"]')!;
      assert.equal(row.querySelector("dt")?.textContent, "NCF / e-CF");
      assert.equal(row.querySelector("dd")?.textContent, "Sin comprobante fiscal");
      assert.equal(section.querySelector('[data-fact="ncf"]'), null);
      assert.equal(section.querySelector('[data-fact="ecf"]'), null);
      assert.ok(!/No registrado|Sin registrar|Not recorded/.test(section.textContent ?? ""));
      await env.act(async () => env.root.unmount());
    }
  });

  test("in English it reads No fiscal receipt number; a record with an NCF shows its number", async () => {
    const english = await facts(null, "en");
    assert.equal(english.host.querySelector('[data-fact="fiscal_number"] dd')?.textContent, "No fiscal receipt number");
    await english.act(async () => english.root.unmount());
    const withNcf = await facts({ rnc: unknown, ncf: { state: "known", value: "B0100000001", origin: "extracted", verified: false, source_ids: ["s"] }, ecf: unknown, itbis: unknown });
    assert.equal(withNcf.host.querySelector('[data-fact="fiscal_number"]'), null);
    assert.equal(withNcf.host.querySelector('[data-fact="ncf"] dd')?.textContent, "B0100000001");
    await withNcf.act(async () => withNcf.root.unmount());
  });
});

describe("one owner for the marks", () => {
  test("the Bandeja row and the record show the same server marks for a grantee's mark, the owner's mark and after an unmark", async () => {
    const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
    const { ReceiptRow } = await import("@/components/business-app/BusinessInboxPanel");
    const { default: ReceiptMarksCard } = await import("@/components/business-app/ReceiptMarksCard");
    const owner = { chosen: null, reload: () => undefined, source: {} } as unknown as BusinessContextValue;
    const cases: { name: string; personal: boolean; by: string | null }[] = [
      { name: "grantee mark", personal: true, by: "Marta" },
      { name: "owner mark", personal: true, by: null },
      { name: "unmarked", personal: false, by: null },
    ];
    for (const item of cases) {
      const server = { personal: item.personal, personal_marked_by: item.by, fiscal_value: "ncf" as const, include_606: null };
      const read = (host: HTMLElement) => ({
        personal: host.querySelector('[data-mark="personal"]') !== null,
        dot: host.querySelector('[data-testid="personal-marked-dot"]') !== null,
        said: host.querySelector('[data-mark="personal"] .sr-only')?.textContent ?? null,
      });
      const env = await setup();
      await env.act(async () => { env.root.render(<env.I18nextProvider i18n={env.i18n}><BusinessContext.Provider value={owner}><ul><ReceiptRow receipt={receipt({ ...server, personal_editable: true })} onOpen={() => undefined} onMark={() => undefined} /></ul></BusinessContext.Provider></env.I18nextProvider>); });
      const row = read(env.host);
      await env.act(async () => { env.root.render(<env.I18nextProvider i18n={env.i18n}><BusinessContext.Provider value={owner}><ReceiptMarksCard dossier={{ draft_id: "d-1", version: 3, capabilities: ["read", "prepare"], history: [], facts: { business_share: { state: "unknown", value: null, origin: null, verified: false, source_ids: [] }, fiscal: null }, ...server } as unknown as BusinessDossier} onChanged={() => undefined} /></BusinessContext.Provider></env.I18nextProvider>); });
      const record = read(env.host);
      assert.deepEqual(record, row, item.name);
      assert.equal(row.said, item.by ? `Marcado por ${item.by}` : null, item.name);
      assert.equal(row.personal, item.personal, item.name);
      await env.act(async () => env.root.unmount());
    }
  });
});

describe("the server states what the browser used to guess", () => {
  test("an unreadable receipt nobody read shows no fiscal chip; a read one without a number does", async () => {
    const env = await setup();
    const { ReceiptRow } = await import("@/components/business-app/BusinessInboxPanel");
    const render = (item: ReceiptSummary) => env.act(async () => { env.root.render(<env.I18nextProvider i18n={env.i18n}><ul><ReceiptRow receipt={item} onOpen={() => undefined} /></ul></env.I18nextProvider>); });
    await render(receipt({ status: "needs_attention", attention: "unreadable" as ReceiptSummary["attention"], merchant: null, amount: null }));
    assert.equal(env.host.querySelector('[data-mark="no_fiscal"]'), null, "nothing read, nothing claimed");
    await render(receipt({ status: "review_ready", fiscal_known: true, fiscal_value: null }));
    assert.equal(env.host.querySelector('[data-mark="no_fiscal"]')?.textContent, "Sin comprobante fiscal");
    await render(receipt({ status: "review_ready", fiscal_known: true, fiscal_value: "ecf" }));
    assert.equal(env.host.querySelector('[data-mark="no_fiscal"]'), null);
    await env.act(async () => env.root.unmount());
  });

  test("the 606 line names whoever answered, even when the owner edited the record afterwards", async () => {
    const env = await setup();
    const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
    const { default: ReceiptMarksCard } = await import("@/components/business-app/ReceiptMarksCard");
    const accountant = { chosen: { space_id: "s", name: "Colmado Peña", grant_id: "g", role: "accountant", capabilities: ["read", "prepare"], access_seen: true }, reload: () => undefined, source: {} } as unknown as BusinessContextValue;
    const ownerEdit = { draft_id: "d-1", version: 5, actor: { actor_id: "o", actor_kind: "member", display_name: "Dueño", grant_id: "own", issuer_id: "o", issuer_display_name: "Dueño" }, before: {}, after: {}, source_ids: [], turn_key: null, created_at: "2026-10-13T11:00:00Z" };
    const record = { draft_id: "d-1", version: 5, capabilities: ["read", "prepare"], history: [ownerEdit], facts: {}, personal: true, fiscal_known: true, fiscal_value: "ncf", include_606: false, include_606_by: "Lía" } as unknown as BusinessDossier;
    await env.act(async () => { env.root.render(<env.I18nextProvider i18n={env.i18n}><BusinessContext.Provider value={accountant}><ReceiptMarksCard dossier={record} onChanged={() => undefined} /></BusinessContext.Provider></env.I18nextProvider>); });
    assert.equal(env.host.querySelector('[data-testid="receipt-606-state"]')?.textContent, "Fuera del 606 por Lía");
    await env.act(async () => env.root.unmount());
  });

  test("the history reads a 606 answer as Sí or No, never true or false", async () => {
    const env = await setup();
    const { default: ReceiptHistory } = await import("@/components/business-app/ReceiptHistory");
    const unknown = { state: "unknown", value: null, origin: null, verified: false, source_ids: [] };
    const base = { kind: unknown, amount: unknown, currency: unknown, occurred_on: unknown, counterparty: unknown, funding: unknown, business_share: unknown, receipt_state: unknown, category_id: unknown };
    const fiscal = (answer: unknown) => ({ rnc: unknown, ncf: { state: "known", value: "B01", origin: "extracted", verified: false, source_ids: ["s"] }, ecf: unknown, itbis: unknown, include_606: answer });
    const revision = { draft_id: "d-1", version: 4, actor: { actor_id: "a", actor_kind: "member", display_name: "Lía", grant_id: "g", issuer_id: "o", issuer_display_name: "Dueño" }, before: { ...base, fiscal: fiscal(unknown) }, after: { ...base, fiscal: fiscal({ state: "known", value: true, origin: "member_set", verified: true, source_ids: ["s"] }) }, source_ids: ["s"], turn_key: null, created_at: "2026-10-13T10:00:00Z" };
    await env.act(async () => { env.root.render(<env.I18nextProvider i18n={env.i18n}><ReceiptHistory history={[revision] as never} accounts={[]} /></env.I18nextProvider>); });
    const text = env.host.textContent ?? "";
    assert.ok(text.includes("Sí"), text);
    assert.ok(!/\btrue\b|\bfalse\b/.test(text), text);
    assert.equal(env.host.querySelector('[data-testid="history-606"] dd')?.textContent, "Pendiente del contador→Sí");
    // A read that creates the record leaves the 606 open: no 606 row, never "Sin registrar".
    const created = { ...revision, version: 1, before: null, after: { ...base, fiscal: fiscal(unknown) } };
    await env.act(async () => { env.root.render(<env.I18nextProvider i18n={env.i18n}><ReceiptHistory history={[created] as never} accounts={[]} /></env.I18nextProvider>); });
    assert.equal(env.host.querySelector('[data-testid="history-606"]'), null);
    assert.ok(!(env.host.textContent ?? "").includes("Incluir en 606"));
    await env.act(async () => env.root.unmount());
  });
});

describe("the Bandeja row menu", () => {
  test("opening and dismissing the menu never opens or changes a receipt", async () => {
    const env = await setup();
    const { ReceiptRow } = await import("@/components/business-app/BusinessInboxPanel");
    let opened = 0;
    let marked = 0;
    await env.act(async () => env.root.render(<env.I18nextProvider i18n={env.i18n}><ul><ReceiptRow receipt={receipt({ personal_editable: true })} onOpen={() => { opened++; }} onMark={() => { marked++; }} /></ul></env.I18nextProvider>));
    const trigger = env.host.querySelector('[aria-haspopup="menu"]') as HTMLButtonElement;
    assert.ok(trigger);
    await env.act(async () => trigger.click());
    const item = env.host.querySelector('[role="menuitem"]') as HTMLButtonElement;
    assert.equal(document.activeElement, item);
    await env.act(async () => item.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
    assert.equal(env.host.querySelector('[role="menu"]'), null);
    assert.equal(document.activeElement, trigger);
    assert.equal(opened, 0);
    assert.equal(marked, 0);
    await env.act(async () => (env.host.querySelector("li > button") as HTMLButtonElement).click());
    assert.equal(opened, 1);
    await env.act(async () => env.root.unmount());
  });
});
