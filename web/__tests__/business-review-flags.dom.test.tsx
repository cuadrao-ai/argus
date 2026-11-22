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
  return { ...dossier, version: dossier.version + 1, review_state: "accepted", approval_available: false, bandeja_group: { group: null, reason: null, label: "accepted" }, listo_gaps: [], approval_result: { status: "recorded", activity_id: "70000000-0000-4000-8000-000000000001", reviewed_version: dossier.version, approved_revision: factsRevision(dossier), approved_at: "2026-10-31T14:40:00Z", actor: dossier.history.at(-1)!.actor } };
}

/** A flagged read with the gaps the server's Bandeja rule gives it. */
async function flagged(codes: readonly ReviewFlagCode[], gaps: readonly ListoGap[]): Promise<BusinessDossier> {
  const dossier = await flaggedReceipt(codes, accounts);
  dossier.listo_gaps = gaps;
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
  const step = () => document.querySelector<HTMLElement>('[data-testid="review-flag-confirm"]');
  const tap = async (label: string, within?: ParentNode) => {
    const target = button(label, within);
    assert.ok(target, `${label} is offered`);
    await act(async () => target.click());
    await settle();
  };
  return {
    act, host, opened, settle, button, step, tap,
    approve: () => tap(copy.approve_action),
    approveAnyway: () => tap(copy.review_flag.approve_anyway, step() ?? undefined),
    // A recorded receipt offers no Aceptar and has no Bandeja pill.
    recorded: () => host.querySelector('[data-testid="receipt-review-footer"]') !== null && host.querySelector("[data-review-primary]") === null && host.querySelector('[data-testid="status-pill"]') === null,
    problems: () => [...(document.querySelector('[data-testid="review-flag-confirm"]')?.querySelectorAll("li") ?? [])].map((item) => item.textContent),
    status: (row: string) => host.querySelector<HTMLElement>(`[data-testid="row-status-${row}"]`),
    close: async () => { await act(async () => root.unmount()); host.remove(); },
  };
}

const copy = es.business.dossier;
const flagCopy = copy.review_flag;

test("an RNC with a wrong check digit opens a step before approval, with Corregir as the primary way out", async () => {
  const { primaryButtonClass, secondaryButtonClass } = await import("@/components/business-app/business-ui");
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
    assert.equal(step.querySelector("h2")?.textContent, "2 por resolver");
    assert.deepEqual(page.problems(), [`${flagCopy.rnc_check_digit.title}. ${flagCopy.rnc_check_digit.text}`, `${copy.placeholder.gap.review_flag.title}. ${copy.placeholder.gap.review_flag.text}`]);
    assert.ok(step.textContent?.includes(flagCopy.export_blocked), "the step says approving anyway still blocks the export");
    const fix = page.button(flagCopy.fix, step);
    const anyway = page.button(flagCopy.approve_anyway, step);
    assert.equal(fix?.className, primaryButtonClass);
    assert.equal(anyway?.className, secondaryButtonClass);
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
    await page.tap(flagCopy.fix, page.step()!);
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

test("Aceptar de todos modos sends approve_anyway and records the receipt", async () => {
  const dossier = await flagged(["rnc_check_digit"], ["invalid_rnc", "review_flag"]);
  const approvals = serve(dossier);
  const page = await render(dossier);
  try {
    await page.approve();
    await page.approveAnyway();
    assert.equal(page.step(), null);
    assert.deepEqual(approvals.map((item) => item.body), [{ version: dossier.version, action: dossier.approval_action, approve_anyway: true }]);
    assert.ok(approvals[0].key, "the request carries a key");
    assert.ok(page.recorded(), "the receipt is recorded");
  } finally {
    await page.close();
  }
});

test("a refusal naming flags the read did not carry opens the step from its context; approving anyway uses a new key", async () => {
  // Read before the server sent review flags, so the read names no gap either.
  const dossier = await flagged(["ncf_malformed"], []);
  delete dossier.review_flags;
  const approvals = serve(dossier, refusal("approval_confirmation_required", { flags: ["ncf_malformed"] }));
  const page = await render(dossier);
  try {
    await page.approve();
    assert.deepEqual(approvals.map((item) => item.body), [{ version: dossier.version, action: dossier.approval_action }]);
    const step = page.step();
    assert.ok(step, "the refusal becomes the step, not a generic error");
    assert.deepEqual([...step.querySelectorAll("li[data-problem]")].map((item) => item.getAttribute("data-problem")), ["ncf_malformed"]);
    assert.equal(step.querySelector("h2")?.textContent, flagCopy.ncf_malformed.title);
    assert.ok(step.textContent?.includes(flagCopy.ncf_malformed.text));
    assert.equal(page.host.textContent?.includes(es.business.dossier.refused), false);
    await page.approveAnyway();
    assert.equal(approvals.length, 2);
    assert.equal(approvals[1].body.approve_anyway, true);
    assert.ok(approvals[0].key && approvals[1].key);
    assert.notEqual(approvals[1].key, approvals[0].key, "approving anyway is a new request, never a replay of the refused one");
    assert.ok(page.recorded(), "the receipt is recorded");
  } finally {
    await page.close();
  }
});

test("Corregir after such a refusal points at the row the refusal's code is about", async () => {
  const dossier = await flagged(["ncf_malformed"], []);
  delete dossier.review_flags;
  const approvals = serve(dossier, refusal("approval_confirmation_required", { flags: ["ncf_malformed"] }));
  const page = await render(dossier);
  try {
    await page.approve();
    await page.tap(flagCopy.fix, page.step()!);
    assert.equal(page.step(), null);
    assert.ok(page.host.querySelector('[data-fact="fiscal_number"]')?.getAttribute("data-flash"), "the NCF row flashes");
    assert.equal(page.host.querySelector('[data-fact="rnc"]')?.getAttribute("data-flash"), null, "and no other");
    assert.equal(approvals.length, 1);
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
    assert.equal(step.querySelector("h2")?.textContent, "3 por resolver");
    assert.deepEqual(page.problems(), [
      `${flagCopy.rnc_check_digit.title}. ${es.business.dgii.rnc_check.invalid_length.reason}`,
      `${flagCopy.ncf_malformed.title}. ${flagCopy.ncf_malformed.text}`,
      `${copy.placeholder.gap.review_flag.title}. ${copy.placeholder.gap.review_flag.text}`,
    ]);
    assert.equal(approvals.length, 0, "nothing is sent while the step is open");
    await page.approveAnyway();
    assert.deepEqual(approvals.map((item) => item.body), [{ version: dossier.version, action: dossier.approval_action, approve_anyway: true }]);
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
    assert.equal(page.step()?.querySelector("h2")?.textContent, copy.placeholder.gap.review_flag.title);
    assert.deepEqual(page.problems(), [`${copy.placeholder.gap.review_flag.title}. ${flagCopy.itbis_high.text}`]);
    assert.equal(approvals.length, 0);
    await page.approveAnyway();
    assert.deepEqual(approvals.map((item) => item.body), [{ version: dossier.version, action: dossier.approval_action, approve_anyway: true }]);
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

test("in English, one step lists every confirm flag and the export line once", async () => {
  const dossier = await flagged(["rnc_check_digit", "ncf_malformed", "itbis_high"], ["invalid_rnc", "invalid_ncf", "review_flag"]);
  const approvals = serve(dossier);
  const page = await render(dossier, "en");
  try {
    const copy = en.business.dossier.review_flag;
    await page.approve();
    const step = page.step();
    assert.ok(step);
    assert.equal(step.querySelector("h2")?.textContent, "3 to resolve");
    assert.deepEqual([...step.querySelectorAll("li strong")].map((item) => item.textContent), [`${copy.rnc_check_digit.title}.`, `${copy.ncf_malformed.title}.`, `${en.business.dossier.placeholder.gap.review_flag.title}.`]);
    assert.equal(step.textContent?.split(copy.export_blocked).length, 2, "the export line shows once");
    await page.approveAnyway();
    assert.deepEqual(approvals.map((item) => item.body), [{ version: dossier.version, action: dossier.approval_action, approve_anyway: true }]);
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
