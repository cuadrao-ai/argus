import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessAccount } from "@/lib/business-api";
import { factsRevision, type BusinessDossier } from "@/lib/business-dossier";
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

/** What the server answers a recorded approval with. Flags are read on every request, so they stay. */
function recorded(dossier: BusinessDossier): BusinessDossier {
  return { ...dossier, version: dossier.version + 1, review_state: "accepted", approval_available: false, approval_result: { status: "recorded", activity_id: "70000000-0000-4000-8000-000000000001", reviewed_version: dossier.version, approved_revision: factsRevision(dossier), approved_at: "2026-10-31T14:40:00Z", actor: dossier.history.at(-1)!.actor } };
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
    recorded: () => [...host.querySelectorAll('[role="status"]')].some((item) => item.querySelector("p")?.textContent === copy.recorded.replace("{{version}}", String(factsRevision(dossier)))),
    close: async () => { await act(async () => root.unmount()); host.remove(); },
  };
}

const flagCopy = es.business.dossier.review_flag;

test("an RNC with a wrong check digit opens a step before approval, with Corregir as the primary way out", async () => {
  const { primaryButtonClass, secondaryButtonClass } = await import("@/components/business-app/business-ui");
  const dossier = await flaggedReceipt(["rnc_check_digit"], accounts);
  const approvals = serve(dossier);
  const page = await render(dossier);
  try {
    assert.equal(page.host.querySelector('[data-fact="rnc"] [data-testid="rnc-status"]')?.getAttribute("data-rnc-status"), "check_digit", "the RNC row names the error before any tap");
    await page.approve();
    const step = page.step();
    assert.ok(step, "approval stops at the step");
    assert.equal(step.getAttribute("role"), "alertdialog");
    assert.deepEqual([...step.querySelectorAll("[data-flag]")].map((item) => item.getAttribute("data-flag")), ["rnc_check_digit"]);
    assert.equal(step.querySelector("h2")?.textContent, flagCopy.rnc_check_digit.title);
    assert.ok(step.textContent?.includes(flagCopy.rnc_check_digit.text));
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

test("Corregir closes the step, approves nothing and puts the cursor on the RNC as read", async () => {
  const dossier = await flaggedReceipt(["rnc_check_digit"], accounts);
  const approvals = serve(dossier);
  const page = await render(dossier);
  try {
    await page.approve();
    await page.tap(flagCopy.fix, page.step()!);
    assert.equal(page.step(), null);
    assert.equal(approvals.length, 0);
    const editor = page.host.querySelector<HTMLDetailsElement>('[data-testid="fiscal-declaration"]');
    assert.equal(editor?.open, true, "the tax details open");
    const rnc = editor.querySelector<HTMLInputElement>('input[name="rnc"]');
    assert.equal(document.activeElement, rnc);
    assert.equal(rnc?.value, READ_VALUES.rnc.flagged);
  } finally {
    await page.close();
  }
});

test("Escape and the backdrop close the step without approving", async () => {
  const dossier = await flaggedReceipt(["rnc_check_digit"], accounts);
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

test("Aprobar de todos modos sends approve_anyway and records the receipt", async () => {
  const dossier = await flaggedReceipt(["rnc_check_digit"], accounts);
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
  const dossier = await flaggedReceipt(["ncf_malformed"], accounts);
  // Read before the server sent review flags.
  delete dossier.review_flags;
  const approvals = serve(dossier, refusal("approval_confirmation_required", { flags: ["ncf_malformed"] }));
  const page = await render(dossier);
  try {
    await page.approve();
    assert.deepEqual(approvals.map((item) => item.body), [{ version: dossier.version, action: dossier.approval_action }]);
    const step = page.step();
    assert.ok(step, "the refusal becomes the step, not a generic error");
    assert.deepEqual([...step.querySelectorAll("[data-flag]")].map((item) => item.getAttribute("data-flag")), ["ncf_malformed"]);
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

test("Corregir after such a refusal opens the tax details, since the read names no field", async () => {
  const dossier = await flaggedReceipt(["ncf_malformed"], accounts);
  delete dossier.review_flags;
  const approvals = serve(dossier, refusal("approval_confirmation_required", { flags: ["ncf_malformed"] }));
  const page = await render(dossier);
  try {
    await page.approve();
    await page.tap(flagCopy.fix, page.step()!);
    const editor = page.host.querySelector<HTMLDetailsElement>('[data-testid="fiscal-declaration"]');
    assert.equal(editor?.open, true);
    assert.equal(document.activeElement, editor.querySelector("summary"));
    assert.equal(approvals.length, 1);
  } finally {
    await page.close();
  }
});

test("a high ITBIS shows on the ITBIS row and approval goes straight through", async () => {
  const dossier = await flaggedReceipt(["itbis_high"], accounts);
  const approvals = serve(dossier);
  const page = await render(dossier);
  try {
    assert.equal(page.host.querySelector('[data-fact="itbis"] [data-testid="itbis-high"]')?.textContent, flagCopy.itbis_high.text);
    await page.approve();
    assert.equal(page.step(), null, "a warning flag asks for nothing");
    assert.deepEqual(approvals.map((item) => item.body), [{ version: dossier.version, action: dossier.approval_action }]);
    assert.ok(page.recorded(), "the receipt is recorded");
  } finally {
    await page.close();
  }
});

test("a duplicate refusal after approving anyway names it and opens the record already approved", async () => {
  const dossier = await flaggedReceipt(["rnc_check_digit"], accounts);
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
  const dossier = await flaggedReceipt([], accounts);
  const approvals = serve(dossier);
  const page = await render(dossier);
  try {
    assert.equal(page.host.querySelector('[data-fact="rnc"] [data-testid="rnc-status"]')?.getAttribute("data-rnc-status"), "unverified");
    assert.equal(page.host.querySelector('[data-testid="itbis-high"]'), null);
    await page.approve();
    assert.equal(page.step(), null);
    assert.deepEqual(approvals.map((item) => item.body), [{ version: dossier.version, action: dossier.approval_action }]);
    assert.ok(page.recorded(), "the receipt is recorded");
  } finally {
    await page.close();
  }
});

test("in English, one step lists every confirm flag and the export line once", async () => {
  const dossier = await flaggedReceipt(["rnc_check_digit", "ncf_malformed", "itbis_high"], accounts);
  const approvals = serve(dossier);
  const page = await render(dossier, "en");
  try {
    const copy = en.business.dossier.review_flag;
    assert.equal(page.host.querySelector('[data-testid="itbis-high"]')?.textContent, copy.itbis_high.text);
    await page.approve();
    const step = page.step();
    assert.ok(step);
    assert.deepEqual([...step.querySelectorAll("h2")].map((item) => item.textContent), [copy.rnc_check_digit.title, copy.ncf_malformed.title]);
    assert.equal(step.textContent?.split(copy.export_blocked).length, 2, "the export line shows once");
    await page.approveAnyway();
    assert.deepEqual(approvals.map((item) => item.body), [{ version: dossier.version, action: dossier.approval_action, approve_anyway: true }]);
  } finally {
    await page.close();
  }
});
