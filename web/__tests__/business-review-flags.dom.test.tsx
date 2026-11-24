import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessAccount } from "@/lib/business-api";
import { factsRevision, type BusinessDossier, type ListoGap, type ReviewFlagCode } from "@/lib/business-dossier";
import type { BusinessContextValue, BusinessPanelState } from "@/components/business-app/BusinessWorkspace";
import { dossierFixtureIds } from "@/components/business-app/dossier-fixtures";
import en from "@/public/locales/en/common.json";
import es from "@/public/locales/es-419/common.json";
import { flaggedReceipt, READ_VALUES, refusal } from "./fixtures/review-flags";

const accounts: BusinessAccount[] = [{ id: "acct-ops", nickname: "Caja", currency: "DOP", type: "cash" }];
const locales = { "es-419": es, en } as const;
type Language = keyof typeof locales;
const original = { fetch: globalThis.fetch, mock: process.env.NEXT_PUBLIC_MOCK_AUTH };
// The tax fields the server lists for a 606 (src/argus/domain/business/dgii_columns.py), the ones a flag can point at.
const fields = { "606": [
  { name: "rnc", label: "RNC o Cédula", kind: "text", options: [] },
  { name: "ncf", label: "NCF", kind: "text", options: [] },
  { name: "itbis", label: "ITBIS Facturado", kind: "money", options: [] },
  { name: "category", label: "Tipo de gasto", kind: "select", options: ["02"], labels: { "02": "Gastos por trabajos, suministros y servicios" } },
], "607": [] };

beforeEach(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
});
afterEach(async () => {
  globalThis.fetch = original.fetch;
  if (original.mock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = original.mock;
  await GlobalRegistrator.unregister();
});

/** What the server answers a recorded approval with. Flags are read on every request, so they stay; the record leaves the Bandeja. */
function recorded(dossier: BusinessDossier): BusinessDossier {
  return { ...dossier, version: dossier.version + 1, review_state: "accepted", approval_available: false, bandeja_group: { group: null, reason: null, label: "accepted" }, listo_gaps: [], confirmable: [], approval_result: { status: "recorded", activity_id: "70000000-0000-4000-8000-000000000001", reviewed_version: dossier.version, approved_revision: factsRevision(dossier), approved_at: "2026-10-31T14:40:00Z", actor: dossier.history.at(-1)!.actor } };
}

/** A flagged read with the gaps the server's Bandeja rule gives it. */
async function flagged(codes: readonly ReviewFlagCode[], gaps: readonly ListoGap[], confirmable = gaps): Promise<BusinessDossier> {
  const dossier = await flaggedReceipt(codes, accounts);
  dossier.listo_gaps = gaps;
  const reasons = {
    invalid_rnc: { field: "rnc", words: "business.transactions.layout.workflow.missing.invalid_rnc" },
    invalid_ncf: { field: "ncf", words: "business.transactions.layout.workflow.missing.invalid_ncf" },
    missing_date: { field: "occurred_on", words: "business.transactions.layout.workflow.missing.missing_date" },
    review_flag: { field: null, words: "business.dossier.placeholder.gap.review_flag.title" },
    unverified_sender: { field: null, words: "business.dossier.placeholder.gap.unverified_sender.title" },
  };
  dossier.reasons = Object.fromEntries(Object.entries(reasons).filter(([code]) => gaps.some(gap => gap === code)));
  dossier.confirmable = confirmable;
  dossier.bandeja_group = gaps.length ? { group: "attention", reason: gaps[0], label: "needs_attention" } : { group: "listo", reason: null, label: "ready" };
  return dossier;
}

type Approval = { body: Record<string, unknown>; key: string | null };

/** One receipt's server. Each approval is answered by the next of `answers`, then by a recorded approval. */
function serve(dossier: BusinessDossier, ...answers: Response[]) {
  const approvals: Approval[] = [];
  globalThis.fetch = async (url, init) => {
    const path = new URL(String(url)).pathname;
    if (path.endsWith("/business/fiscal-profile/fields")) return Response.json(fields);
    if (path.endsWith(`/business/drafts/${dossier.draft_id}/dossier`)) return Response.json(dossier);
    if (path.endsWith(`/business/drafts/${dossier.draft_id}/approve`) && init?.method === "POST") {
      approvals.push({ body: JSON.parse(String(init.body)), key: new Headers(init.headers).get("Idempotency-Key") });
      return answers.shift() ?? Response.json(recorded(dossier));
    }
    return Response.json({ code: "not_found" }, { status: 404 });
  };
  return approvals;
}

async function render(dossier: BusinessDossier, language: Language = "es-419") {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { liveBusinessDataSource } = await import("@/components/business-app/business-data");
  const { default: Review } = await import("@/components/business-app/ReceiptDossierReview");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: language, resources: { [language]: { translation: locales[language] } }, interpolation: { escapeValue: false } });
  const opened: BusinessPanelState[] = [];
  const context = {
    source: liveBusinessDataSource,
    reload: () => undefined,
    records: { inbox: [], notes: [], notesError: false, notesTruncated: false, error: false, workspace: null },
    guardPanel: () => () => undefined,
    openPanel: (panel: BusinessPanelState) => { opened.push(panel); },
    actions: { create: [] },
    panel: { kind: "draft", draftId: dossier.draft_id },
    chosen: null,
    revision: 0,
  } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}><Review draftId={dossier.draft_id} /></BusinessContext.Provider></I18nextProvider>); });
  const settle = async () => { for (let turn = 0; turn < 5; turn += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); }); };
  await settle();
  const copy = locales[language].business.dossier;
  const button = (label: string, within: ParentNode = document) => [...within.querySelectorAll("button")].find((item) => item.textContent === label);
  const step = () => document.querySelector<HTMLElement>('[data-testid="dossier-confirm"]');
  const tap = async (label: string, within?: ParentNode) => {
    const target = button(label, within);
    assert.ok(target, `${label} is offered`);
    await act(async () => target.click());
    await settle();
  };
  return {
    act, host, opened, settle, button, step, tap,
    approve: () => tap(copy.approve_action),
    approveAnyway: () => tap(copy.confirm.accept_anyway, step() ?? undefined),
    // A recorded receipt offers no Aceptar and has no Bandeja pill.
    recorded: () => host.querySelector('[data-testid="receipt-review-footer"]') !== null && host.querySelector("[data-review-primary]") === null && host.querySelector('[data-testid="status-pill"]') === null,
    problems: () => [...(document.querySelector('[data-testid="dossier-confirm"]')?.querySelectorAll("li p") ?? [])].map((item) => item.textContent),
    status: (row: string) => host.querySelector<HTMLElement>(`[data-testid="row-status-${row}"]`),
    close: async () => { await act(async () => root.unmount()); host.remove(); },
  };
}

const copy = es.business.dossier;
const flagCopy = copy.review_flag;

test("an RNC with a wrong check digit opens a step before approval, with Corregir as the primary way out", async () => {
  const dossier = await flagged(["rnc_check_digit"], ["invalid_rnc", "review_flag"]);
  const approvals = serve(dossier);
  const page = await render(dossier);
  try {
    assert.equal(page.status("rnc")?.getAttribute("data-status"), "warn", "the RNC row names the error before any tap");
    assert.ok(page.status("rnc")?.getAttribute("aria-label")?.includes(flagCopy.rnc_check_digit.text));
    await page.approve();
    const step = page.step();
    assert.ok(step, "approval stops at the step");
    assert.equal(step.getAttribute("role"), "alertdialog");
    assert.equal(step.querySelector("h2")?.textContent, "¿Aceptar con 2 datos por revisar?");
    assert.deepEqual(page.problems(), [`${flagCopy.rnc_check_digit.title}. ${flagCopy.rnc_check_digit.text}`, copy.placeholder.gap.review_flag.text]);
    assert.doesNotMatch(step.textContent ?? "", /606/);
    const fix = page.button(copy.confirm.fix, step);
    const anyway = page.button(copy.confirm.accept_anyway, step);
    assert.match(fix?.className ?? "", /min-h-11.*cuadrao-green/);
    assert.match(anyway?.className ?? "", /min-h-11.*border/);
    assert.equal(document.activeElement, fix, "the cursor starts on Corregir");
    assert.equal(approvals.length, 0, "nothing is sent while the step is open");
  } finally {
    await page.close();
  }
});

test("Corregir closes the step, approves nothing and points at the RNC row", async () => {
  const dossier = await flagged(["rnc_check_digit"], ["invalid_rnc", "review_flag"]);
  const approvals = serve(dossier);
  const page = await render(dossier);
  try {
    assert.equal(page.host.querySelector('[data-fact="rnc"]')?.getAttribute("data-flash"), null);
    await page.approve();
    await page.tap(copy.confirm.fix, page.step()!);
    assert.equal(page.step(), null);
    assert.equal(approvals.length, 0);
    assert.ok(page.host.querySelector('[data-fact="rnc"]')?.getAttribute("data-flash"), "the RNC's own row flashes");
  } finally {
    await page.close();
  }
});

test("an RNC error says it once, with no revisar on the row, and the pencil opens the RNC as read", async () => {
  const dossier = await flagged(["rnc_check_digit", "itbis_high"], ["invalid_rnc", "review_flag"]);
  serve(dossier);
  const page = await render(dossier);
  try {
    const row = (key: string) => page.host.querySelector<HTMLElement>(`[data-fact="${key}"]`)!;
    assert.equal(page.status("rnc")?.getAttribute("aria-label"), flagCopy.rnc_check_digit.text, "the RNC row says its error once, not revisar");
    assert.equal(page.status("itbis")?.getAttribute("aria-label"), flagCopy.itbis_high.text, "the high ITBIS line says it once, not revisar");
    const [pencil, ...others] = row("rnc").querySelectorAll("button[aria-label]");
    assert.equal(pencil?.getAttribute("aria-label"), `${copy.edit} · RNC`);
    assert.equal(others.length, 0, "the pencil is the row's one action");
    await page.act(async () => pencil.click());
    await page.settle();
    const rnc = page.host.querySelector<HTMLInputElement>('[data-testid="edit-rnc"] input');
    assert.equal(document.activeElement, rnc, "the RNC's own row opens");
    assert.equal(rnc?.value, READ_VALUES.rnc.flagged);
  } finally {
    await page.close();
  }
});

test("an e-CF that disputes the RNC read leaves no revisar on the RNC row", async () => {
  const dossier = await flagged([], []);
  dossier.ecf_checks = { encf: null, tipo_ecf: null, checked_at: "2026-10-10T14:25:00Z", checks: [{ name: "read_matches_xml", state: "failed", code: "read_differs", detail: { rnc: `read=${READ_VALUES.rnc.clean} xml=${READ_VALUES.rnc.flagged}` } }] } as unknown as BusinessDossier["ecf_checks"];
  serve(dossier);
  const page = await render(dossier);
  try {
    assert.notEqual(page.status("rnc")?.getAttribute("aria-label"), copy.placeholder.doubtful_read);
  } finally {
    await page.close();
  }
});

test("the date the XML disputes says revisar on its row", async () => {
  const dossier = await flagged([], []);
  dossier.ecf_checks = { encf: "E310000000777", tipo_ecf: "31", checked_at: "2026-10-10T14:25:00Z", checks: [{ name: "read_matches_xml", state: "failed", code: "read_differs", detail: { occurred_on: "read=2026-10-09 xml=2026-10-08" } }] };
  serve(dossier);
  const page = await render(dossier);
  try {
    assert.equal(page.status("occurred_on")?.getAttribute("data-status"), "warn");
    assert.equal(page.status("occurred_on")?.getAttribute("aria-label"), copy.placeholder.doubtful_read);
  } finally {
    await page.close();
  }
});

test("Escape and the backdrop close the step without approving", async () => {
  const dossier = await flagged(["rnc_check_digit"], ["invalid_rnc", "review_flag"]);
  const approvals = serve(dossier);
  const page = await render(dossier);
  try {
    await page.approve();
    await page.act(async () => document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
    await page.settle();
    assert.equal(page.step(), null);
    await page.approve();
    const backdrop = page.step()?.parentElement?.querySelector<HTMLButtonElement>(`button[aria-label="${es.common.cancel}"]`);
    assert.ok(backdrop);
    await page.act(async () => backdrop.click());
    await page.settle();
    assert.equal(page.step(), null);
    assert.equal(approvals.length, 0);
  } finally {
    await page.close();
  }
});

test("Aceptar de todos modos sends every confirmed gap and the suggestion shown on screen", async () => {
  const dossier = await flagged(["rnc_check_digit"], ["invalid_rnc", "review_flag"]);
  const suggestions = { category: { value: "02", source: "last_choice" } } as const;
  dossier.declaration_suggestions = { ...suggestions, payment_method: null };
  const approvals = serve(dossier);
  const page = await render(dossier);
  try {
    await page.approve();
    await page.approveAnyway();
    assert.equal(page.step(), null);
    assert.deepEqual(approvals.map((item) => item.body), [{ version: dossier.version, action: dossier.approval_action, accept_gaps: dossier.listo_gaps, suggestions }]);
    assert.ok(approvals[0].key, "the request carries a key");
    assert.ok(page.recorded(), "the receipt is recorded");
  } finally {
    await page.close();
  }
});

test("a refusal updates the dialog and the next approval names the new gaps with a new key", async () => {
  const dossier = await flagged(["ncf_malformed"], ["invalid_ncf"]);
  const updated = ["invalid_ncf", "missing_itbis"] satisfies ListoGap[];
  const approvals = serve(dossier, refusal("not_listo", { gaps: updated, confirmable: updated }));
  const page = await render(dossier);
  try {
    await page.approve();
    await page.approveAnyway();
    const step = page.step();
    assert.ok(step, "the refusal opens a new confirmation");
    assert.deepEqual(page.problems(), [
      `${flagCopy.ncf_malformed.title}. ${flagCopy.ncf_malformed.text}`,
      `${copy.placeholder.gap.missing_itbis.title}. ${copy.placeholder.gap.missing_itbis.text}`,
    ]);
    assert.equal(approvals.length, 1, "the new gaps need their own confirmation");
    await page.approveAnyway();
    assert.deepEqual(approvals.map((item) => item.body), [
      { version: dossier.version, action: dossier.approval_action, accept_gaps: ["invalid_ncf"] },
      { version: dossier.version, action: dossier.approval_action, accept_gaps: updated },
    ]);
    assert.ok(approvals[0].key && approvals[1].key);
    assert.notEqual(approvals[1].key, approvals[0].key);
    assert.ok(page.recorded(), "the receipt is recorded");
  } finally {
    await page.close();
  }
});

test("Corregir after a refusal points at its first gap even when the dossier showed Listo", async () => {
  const dossier = await flagged([], []);
  const current = await flagged(["ncf_malformed"], ["missing_date", "invalid_ncf"], ["invalid_ncf"]);
  const approvals = serve(dossier, refusal("not_listo", { gaps: ["missing_date", "invalid_ncf"], confirmable: ["invalid_ncf"] }));
  const page = await render(dossier);
  const label = () => page.host.querySelector('[data-testid="status-pill"]')?.getAttribute("data-label");
  try {
    await page.approve();
    const step = page.step();
    assert.ok(step);
    assert.deepEqual([...step.querySelectorAll("button")].filter(button => !button.closest("li")).map((button) => button.textContent), [copy.confirm.fix]);
    assert.equal(label(), "ready");
    assert.equal(page.host.querySelector('[data-testid="dossier-problems"]'), null, "the refusal only updates the dialog");
    Object.assign(dossier, current);
    await page.tap(copy.confirm.fix, step);
    assert.equal(page.step(), null);
    assert.ok(page.host.querySelector('[data-fact="occurred_on"]')?.getAttribute("data-flash"), "the date row flashes");
    assert.equal(document.activeElement, page.host.querySelector('[data-fact="occurred_on"] button[data-row-value]'));
    assert.equal(label(), "needs_attention");
    await page.approve();
    assert.ok(page.step(), "the latest gaps remain after closing the dialog");
    assert.deepEqual([...page.step()!.querySelectorAll("button")].filter(button => !button.closest("li")).map((button) => button.textContent), [copy.confirm.fix]);
    assert.equal(approvals.length, 1);
    assert.deepEqual(approvals[0].body, { version: dossier.version, action: dossier.approval_action });
  } finally {
    await page.close();
  }
});

for (const origin of ["dossier", "refusal"] as const) {
  test(`closing a hard gap from the ${origin} rechecks a sender cleared at the same version`, async () => {
    const gaps = ["invalid_ncf", "unverified_sender"] satisfies ListoGap[];
    const dossier = origin === "dossier" ? await flagged(["ncf_malformed"], gaps, ["invalid_ncf"]) : await flagged(["ncf_malformed"], []);
    const current = await flagged(["ncf_malformed"], ["invalid_ncf"]);
    const approvals = serve(dossier, ...(origin === "refusal" ? [refusal("not_listo", { gaps, confirmable: ["invalid_ncf"] })] : []));
    const page = await render(dossier);
    try {
      await page.approve();
      assert.ok(page.step());
      assert.equal(page.button(copy.confirm.accept_anyway, page.step()!), undefined);
      assert.equal(dossier.version, current.version);
      Object.assign(dossier, current);
      await page.act(async () => document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
      await page.settle();
      await page.approve();
      assert.equal(page.step()?.querySelector("h2")?.textContent, "¿Aceptar con 1 dato por revisar?");
      assert.deepEqual(page.problems(), [`${flagCopy.ncf_malformed.title}. ${flagCopy.ncf_malformed.text}`]);
      await page.approveAnyway();
      assert.deepEqual(approvals.at(-1)?.body, { version: dossier.version, action: dossier.approval_action, accept_gaps: ["invalid_ncf"] });
      assert.ok(page.recorded());
    } finally {
      await page.close();
    }
  });
}

test("a read that restarted is listed and offers only Corregir", async () => {
  const dossier = await flagged([], []);
  const approvals = serve(dossier, refusal("not_listo", { gaps: ["reading"], confirmable: [] }));
  const page = await render(dossier);
  try {
    await page.approve();
    const step = page.step();
    assert.ok(step);
    assert.equal(step.querySelector("h2")?.textContent, "¿Aceptar con 1 dato por revisar?");
    assert.deepEqual(page.problems(), ["Lectura en curso. Espera a que termine la lectura."]);
    assert.deepEqual([...step.querySelectorAll("button")].filter(button => !button.closest("li")).map((button) => button.textContent), [copy.confirm.fix]);
    assert.equal(approvals.length, 1);
    await page.tap(copy.confirm.fix, step);
    await page.approve();
    assert.equal(approvals.length, 2, "the owner can try again after the read finishes");
    assert.deepEqual(approvals[1].body, approvals[0].body);
    assert.notEqual(approvals[1].key, approvals[0].key, "a new request must not replay the saved refusal");
    assert.ok(page.recorded());
  } finally {
    await page.close();
  }
});

test("mixed gaps list every issue and offer only Corregir", async () => {
  const dossier = await flagged(["ncf_malformed"], ["invalid_ncf", "unverified_sender"], ["invalid_ncf"]);
  const approvals = serve(dossier);
  const page = await render(dossier);
  try {
    await page.approve();
    const step = page.step();
    assert.ok(step);
    assert.deepEqual(page.problems(), [
      `${flagCopy.ncf_malformed.title}. ${flagCopy.ncf_malformed.text}`,
      `${copy.placeholder.gap.unverified_sender.title}. ${copy.placeholder.gap.unverified_sender.text}`,
    ]);
    assert.deepEqual([...step.querySelectorAll("button")].filter(button => !button.closest("li")).map((button) => button.textContent), [copy.confirm.fix]);
    assert.deepEqual(approvals, []);
  } finally {
    await page.close();
  }
});

test("an RNC of the wrong length and the flags share one step before anything is sent", async () => {
  // The server checks the digit only on 9 or 11 digits, so eight digits carry no RNC flag; the length alone makes it invalid.
  const dossier = await flagged(["ncf_malformed"], ["invalid_rnc", "invalid_ncf", "review_flag"]);
  dossier.facts.fiscal!.rnc = { state: "known", value: READ_VALUES.rnc.clean.slice(0, 8), origin: "extracted", verified: false, source_ids: [] };
  const approvals = serve(dossier);
  const page = await render(dossier);
  try {
    await page.approve();
    const step = page.step();
    assert.ok(step, "one step");
    assert.equal(document.querySelectorAll('[role="alertdialog"]').length, 1, "with no second RNC dialog");
    assert.equal(step.querySelector("h2")?.textContent, "¿Aceptar con 3 datos por revisar?");
    assert.deepEqual(page.problems(), [
      `${flagCopy.rnc_check_digit.title}. ${es.business.dgii.rnc_check.invalid_length.reason}`,
      `${flagCopy.ncf_malformed.title}. ${flagCopy.ncf_malformed.text}`,
      copy.placeholder.gap.review_flag.text,
    ]);
    assert.equal(approvals.length, 0, "nothing is sent while the step is open");
    await page.approveAnyway();
    assert.deepEqual(approvals.map((item) => item.body), [{ version: dossier.version, action: dossier.approval_action, accept_gaps: dossier.listo_gaps }]);
    assert.ok(page.recorded(), "the receipt is recorded");
  } finally {
    await page.close();
  }
});

test("a high ITBIS shows on the ITBIS row, and as the server's reason it asks before approval", async () => {
  const dossier = await flagged(["itbis_high"], ["review_flag"]);
  const approvals = serve(dossier);
  const page = await render(dossier);
  try {
    assert.equal(page.status("itbis")?.getAttribute("aria-label"), flagCopy.itbis_high.text);
    await page.approve();
    assert.equal(page.step()?.querySelector("h2")?.textContent, "¿Aceptar con 1 dato por revisar?");
    assert.deepEqual(page.problems(), [flagCopy.itbis_high.text]);
    assert.equal(approvals.length, 0);
    await page.approveAnyway();
    assert.deepEqual(approvals.map((item) => item.body), [{ version: dossier.version, action: dossier.approval_action, accept_gaps: dossier.listo_gaps }]);
    assert.ok(page.recorded(), "the receipt is recorded");
  } finally {
    await page.close();
  }
});

test("a duplicate refusal after approving anyway names it and opens the record already approved", async () => {
  const dossier = await flagged(["rnc_check_digit"], ["invalid_rnc", "review_flag"]);
  const existing = dossierFixtureIds.ready;
  const approvals = serve(dossier, refusal("duplicate_comprobante", { existing_record_id: existing }));
  const page = await render(dossier);
  try {
    await page.approve();
    await page.approveAnyway();
    assert.equal(approvals.length, 1);
    const notice = page.host.querySelector('[data-testid="dossier-duplicate"]');
    assert.equal(notice?.querySelector("p")?.textContent, es.business.dossier.duplicate_recorded);
    assert.equal(page.step(), null);
    await page.tap(es.business.dossier.see_recorded, notice!);
    assert.deepEqual(page.opened, [{ kind: "draft", draftId: existing }]);
  } finally {
    await page.close();
  }
});

test("a receipt with no flags approves at once, as before", async () => {
  const dossier = await flagged([], []);
  const approvals = serve(dossier);
  const page = await render(dossier);
  try {
    assert.equal(page.status("rnc")?.getAttribute("data-status") === "warn", false, "no problem on the RNC row");
    assert.equal(page.status("itbis")?.getAttribute("data-status") === "warn", false, "nor on the ITBIS row");
    await page.approve();
    assert.equal(page.step(), null);
    assert.deepEqual(approvals.map((item) => item.body), [{ version: dossier.version, action: dossier.approval_action }]);
    assert.ok(page.recorded(), "the receipt is recorded");
  } finally {
    await page.close();
  }
});

test("in English, one step lists every gap", async () => {
  const dossier = await flagged(["rnc_check_digit", "ncf_malformed", "itbis_high"], ["invalid_rnc", "invalid_ncf", "review_flag"]);
  const approvals = serve(dossier);
  const page = await render(dossier, "en");
  try {
    const copy = en.business.dossier.review_flag;
    await page.approve();
    const step = page.step();
    assert.ok(step);
    assert.equal(step.querySelector("h2")?.textContent, "Accept with 3 items to review?");
    assert.deepEqual([...step.querySelectorAll("li p")].map((item) => item.textContent), [`${copy.rnc_check_digit.title}. ${copy.rnc_check_digit.text}`, `${copy.ncf_malformed.title}. ${copy.ncf_malformed.text}`, copy.itbis_high.text]);
    assert.doesNotMatch(step.textContent ?? "", /606/);
    await page.approveAnyway();
    assert.deepEqual(approvals.map((item) => item.body), [{ version: dossier.version, action: dossier.approval_action, accept_gaps: dossier.listo_gaps }]);
  } finally {
    await page.close();
  }
});

for (const field of ["net_amount", "legal_tip"] as const) {
  test(`${field} uses the Montos write, with its own row save and server version`, async () => {
    const dossier = await flaggedReceipt([], accounts);
    dossier.net_amount = { amount: "1000.00", source: "calculated" };
    dossier.facts.legal_tip = { state: "known", value: "100.00", origin: "extracted", verified: false, source_ids: [] };
    serve(dossier);
    const previous = globalThis.fetch;
    const writes: Record<string, unknown>[] = [];
    globalThis.fetch = async (url, init) => {
      if (new URL(String(url)).pathname.endsWith("/review") && init?.method === "PATCH") {
        writes.push(JSON.parse(String(init.body)));
        return Response.json({ ...dossier, version: dossier.version + 1, net_amount: { amount: "900.00", source: "edited" } });
      }
      return previous(url, init);
    };
    const page = await render(dossier);
    try {
      const open = page.host.querySelector<HTMLButtonElement>(`[data-fact="${field}"] button`)!;
      await page.act(async () => open.click());
      const input = page.host.querySelector<HTMLInputElement>(`input[data-testid="dossier-review-${field}"]`)!;
      assert.ok(input);
      if (field === "net_amount") assert.match(input.value, /1,000\.00/);
      await page.act(async () => {
        input.setSelectionRange(0, input.value.length);
        input.dispatchEvent(new InputEvent("beforeinput", { inputType: "insertText", data: "900.00", bubbles: true, cancelable: true }));
      });
      const save = page.host.querySelector<HTMLButtonElement>(`[data-fact="${field}"] button[aria-label^="Guardar"]`)!;
      await page.act(async () => save.click());
      await page.settle();
      assert.deepEqual(writes, [{ version: dossier.version, montos: { [field]: { state: "known", value: "900.00" } } }]);
      assert.equal(page.host.querySelector(`[data-fact="${field}"] [data-row-open]`), null);
    } finally { await page.close(); }
  });
}
