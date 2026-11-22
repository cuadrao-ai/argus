import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReactNode } from "react";
import type { BusinessAccount, GrantedSpace, ReceiptDetail, ReceiptSummary } from "@/lib/business-api";
import type { BusinessDossier } from "@/lib/business-dossier";
import type { BusinessContextValue, BusinessPanelState } from "@/components/business-app/BusinessWorkspace";
import { createDossierFixtures, dossierFixtureIds } from "@/components/business-app/dossier-fixtures";

const accounts: BusinessAccount[] = [{ id: "acct-ops", nickname: "Caja", currency: "DOP", type: "cash" }];
const original = { fetch: globalThis.fetch, mock: process.env.NEXT_PUBLIC_MOCK_AUTH };
const client: GrantedSpace = { space_id: "client-space", name: "Colmado de prueba", grant_id: "grant-client", role: "accountant", capabilities: ["read", "prepare"], access_seen: true };

beforeEach(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  globalThis.fetch = async () => Response.json({ code: "not_found" }, { status: 404 });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
});
afterEach(async () => {
  globalThis.fetch = original.fetch;
  if (original.mock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = original.mock;
  await GlobalRegistrator.unregister();
});

async function render(node: (context: BusinessContextValue) => ReactNode, overrides: Partial<BusinessContextValue> = {}) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { liveBusinessDataSource } = await import("@/components/business-app/business-data");
  const es = (await import("@/public/locales/es-419/common.json")).default;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: es } }, interpolation: { escapeValue: false } });
  const opened: BusinessPanelState[] = [];
  const uploads: string[] = [];
  const context = {
    source: liveBusinessDataSource,
    reload: () => undefined,
    records: { inbox: [], notes: [], notesError: false, notesTruncated: false, error: false, workspace: null },
    openPanel: (panel: BusinessPanelState) => { opened.push(panel); },
    actions: { create: [{ id: "upload_receipt", label: "Subir recibo", icon: () => null, run: () => { uploads.push("upload"); } }] },
    panel: { kind: "inbox" },
    chosen: client,
    revision: 0,
    ...overrides,
  } as unknown as BusinessContextValue;
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}>{node(context)}</BusinessContext.Provider></I18nextProvider>); });
  const settle = async () => { for (let turn = 0; turn < 5; turn += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); }); };
  await settle();
  const button = (label: string) => [...host.querySelectorAll("button")].find((item) => item.textContent === label);
  return { act, host, opened, uploads, settle, button, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

/** A fiscal receipt whose RNC has the right length, so Aceptar goes straight to the server. */
async function fiscalDossier(): Promise<BusinessDossier> {
  const dossier = await createDossierFixtures(accounts).dossier(dossierFixtureIds.fiscal);
  assert.ok(dossier.facts.fiscal);
  dossier.facts.fiscal.rnc = { state: "known", value: "101123456", origin: "matched", verified: true, source_ids: [] };
  return dossier;
}

function serveDossier(dossier: BusinessDossier, approve: () => Response) {
  const approvals: string[] = [];
  globalThis.fetch = async (url, init) => {
    const path = new URL(String(url)).pathname;
    if (path.endsWith(`/business/drafts/${dossier.draft_id}/dossier`)) return Response.json(dossier);
    if (path.endsWith(`/business/drafts/${dossier.draft_id}/approve`) && init?.method === "POST") {
      approvals.push(String(init.body));
      return approve();
    }
    return Response.json({ code: "not_found" }, { status: 404 });
  };
  return approvals;
}

test("a duplicate comprobante refusal names it and opens the record already approved", async () => {
  const dossier = await fiscalDossier();
  const existing = dossierFixtureIds.ready;
  const approvals = serveDossier(dossier, () => Response.json(
    { code: "duplicate_comprobante", title: "Duplicate comprobante", detail: "duplicate_comprobante", context: { existing_record_id: existing } },
    { status: 422 },
  ));
  const { default: Review } = await import("@/components/business-app/ReceiptDossierReview");
  const page = await render(() => <Review draftId={dossier.draft_id} />);
  try {
    const approve = page.button("Aceptar");
    assert.ok(approve, "approval is offered");
    await page.act(async () => approve.click());
    await page.settle();
    assert.equal(approvals.length, 1);
    const notice = page.host.querySelector('[data-testid="dossier-duplicate"]');
    assert.ok(notice, "the refusal is shown");
    assert.equal(notice.getAttribute("role"), "alert");
    assert.match(notice.textContent ?? "", /Ya registraste este comprobante\./);
    assert.equal((page.host.textContent ?? "").includes("Esta acción no se pudo completar"), false);
    const see = page.button("Ver el registrado");
    assert.ok(see, "the recorded one is one tap away");
    await page.act(async () => see.click());
    assert.deepEqual(page.opened, [{ kind: "draft", draftId: existing }]);
  } finally {
    await page.close();
  }
});

test("a duplicate refusal without an id still says so, with no dead button", async () => {
  const dossier = await fiscalDossier();
  serveDossier(dossier, () => Response.json({ code: "duplicate_comprobante", title: "Duplicate comprobante", detail: "duplicate_comprobante" }, { status: 422 }));
  const { default: Review } = await import("@/components/business-app/ReceiptDossierReview");
  const page = await render(() => <Review draftId={dossier.draft_id} />);
  try {
    await page.act(async () => page.button("Aceptar")!.click());
    await page.settle();
    assert.match(page.host.querySelector('[data-testid="dossier-duplicate"]')?.textContent ?? "", /Ya registraste este comprobante\./);
    assert.equal(page.button("Ver el registrado"), undefined);
  } finally {
    await page.close();
  }
});

test("a disabled Aceptar has its reason beside the pill, and the reason points at the row the server blocks on", async () => {
  const dossier = await createDossierFixtures(accounts).dossier(dossierFixtureIds.ready);
  dossier.approval_available = false;
  dossier.blockers = [{ code: "fact_required", field: "funding" }, { code: "fact_required", field: "business_share" }];
  // The server's rule says a blocked draft is not Listos.
  dossier.bandeja_group = { group: "attention", reason: "blocked", label: "needs_attention" };
  dossier.listo_gaps = ["blocked"];
  serveDossier(dossier, () => Response.json(dossier));
  const { default: Review } = await import("@/components/business-app/ReceiptDossierReview");
  const page = await render(() => <Review draftId={dossier.draft_id} />);
  try {
    const approve = page.button("Aceptar");
    assert.ok(approve);
    assert.equal(approve.disabled, true);
    assert.equal(page.host.querySelector('[data-testid="approve-reason"]'), null, "the footer holds the action; the header says why");
    const reason = page.host.querySelector<HTMLButtonElement>('[data-testid="dossier-reason"]');
    assert.equal(reason?.textContent, "Tiene algo pendiente");
    await page.act(async () => reason!.click());
    assert.ok(page.host.querySelector('[data-fact="funding"]')?.getAttribute("data-flash"), "the jump lands on the row the first blocker names");
  } finally {
    await page.close();
  }
});

function notReceipt(): ReceiptSummary {
  return {
    id: "20000000-0000-4000-8000-000000000001", channel: "web", filename: "foto-perro.jpg", media_type: "image/jpeg", size_bytes: 2048,
    received_at: "2026-10-19T12:00:00Z", status: "needs_attention", error_code: "not_a_receipt", attention: "not_a_receipt",
    preparable: false, enterable: true, expense_id: null, merchant: null, occurred_on: null, amount: null, currency: null,
    category_id: null, account_id: null,
  };
}

test("a client's record for a file that is not a receipt says so and offers Subir otro documento", async () => {
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { liveBusinessDataSource } = await import("@/components/business-app/business-data");
  const { default: ReceiptReviewPanel } = await import("@/components/business-app/ReceiptReviewPanel");
  const base = await createFixtureBusinessDataSource().receipt("rcpt-blurry");
  assert.ok(base.record_context);
  const detail = { ...base, ...notReceipt(), draft_id: null, activity: null, record_context: { ...base.record_context, capabilities: ["read", "prepare"] } } as ReceiptDetail;
  const receipt = notReceipt();
  const page = await render(() => <ReceiptReviewPanel target={{ kind: "receipt", id: receipt.id }} />, { source: { ...liveBusinessDataSource, receipt: async () => detail } } as Partial<BusinessContextValue>);
  try {
    const notice = page.host.querySelector('[data-testid="receipt-attention"]');
    assert.equal(notice?.querySelector("h3")?.textContent, "Esto no parece un recibo");
    assert.equal(notice?.textContent?.includes("borroso"), false);
    const labels = [...page.host.querySelectorAll('[data-testid="receipt-review-footer"] button:not([aria-label])')].map((button) => button.textContent);
    assert.deepEqual(labels, ["Subir otro documento"], "a prepare grant can upload another document");
    await page.act(async () => page.button("Subir otro documento")!.click());
    assert.deepEqual(page.uploads, ["upload"]);
  } finally {
    await page.close();
  }
});

const UNREAD_NEEDS = ["account_id", "amount", "currency", "occurred_on"];
const failedRead = { attention: "unreadable", error_code: "encrypted_document", preparable: false, enterable: true, version: 0, draft_id: null, missing_fields: UNREAD_NEEDS, activity: { state: "read_failed", unread: false, completion_cursor: null } };
const NO_DRAFT = [
  ["a failed read", failedRead],
  ["a read that can be retried", { ...failedRead, attention: "ai_unavailable", error_code: "extraction_provider_failed", preparable: true }],
  ["a hand-off that stopped", { ...failedRead, attention: "interrupted", error_code: "business_preparation_binding_missing", preparable: true }],
] as const;

for (const [name, state] of NO_DRAFT) {
  test(`${name} with no draft shows the original and its reason, and asks for no Categoría or Pagado desde`, async () => {
    const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
    const { liveBusinessDataSource } = await import("@/components/business-app/business-data");
    const { default: ReceiptReviewPanel } = await import("@/components/business-app/ReceiptReviewPanel");
    const base = await createFixtureBusinessDataSource().receipt("rcpt-blurry");
    const detail = { ...base, ...notReceipt(), ...state } as ReceiptDetail;
    const page = await render(() => <ReceiptReviewPanel target={{ kind: "receipt", id: detail.id }} />, { source: { ...liveBusinessDataSource, receipt: async () => detail } });
    try {
      assert.ok(page.host.querySelector('[data-testid="receipt-attention"]'), "the reason");
      assert.ok(page.host.querySelector('[data-testid="receipt-review-source"]'), "the original");
      assert.equal(page.host.querySelector('[data-testid="receipt-review-fields"] input, [data-testid="receipt-review-fields"] select'), null);
      assert.equal(/Pagado desde|Categoría|Guardar/.test(page.host.textContent ?? ""), false);
    } finally {
      await page.close();
    }
  });
}

test("a record the server has not prepared falls back to the same plain state", async () => {
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { liveBusinessDataSource } = await import("@/components/business-app/business-data");
  const { default: ReceiptReviewPanel } = await import("@/components/business-app/ReceiptReviewPanel");
  const base = await createFixtureBusinessDataSource().receipt("rcpt-blurry");
  const detail = { ...base, ...notReceipt(), status: "review_ready", attention: null, error_code: null, enterable: false, draft_id: dossierFixtureIds.unprepared } as ReceiptDetail;
  const fixtures = createDossierFixtures(accounts);
  const page = await render(() => <ReceiptReviewPanel target={{ kind: "receipt", id: detail.id }} />, { source: { ...liveBusinessDataSource, receipt: async () => detail, dossier: fixtures.dossier } });
  try {
    assert.ok(page.button("Consultar registro actual"), "a way to check again");
    assert.equal(page.host.querySelector('[data-testid="receipt-review-fields"] input, [data-testid="receipt-review-fields"] select'), null);
    assert.equal(/Pagado desde|Categoría/.test(page.host.textContent ?? ""), false);
  } finally {
    await page.close();
  }
});

test("the sample's first row and Papelería Central open their dossier", async () => {
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  for (const [id, name] of [["rcpt-ferreteria", "Ferretería La Esquina"], ["rcpt-papeleria", "Papelería Central"]]) {
    const receipt = await source.receipt(id);
    assert.ok(receipt.draft_id, id);
    const dossier = await source.dossier(receipt.draft_id);
    assert.equal(dossier.sin_comprobante, true, id);
    assert.equal(dossier.facts.counterparty.value, name);
  }
});

/** A read that failed and can be read again, opened by someone who may prepare it, with a working "Leer de nuevo". */
async function openRetryable(state: Pick<ReceiptDetail, "attention" | "error_code">) {
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { liveBusinessDataSource } = await import("@/components/business-app/business-data");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { default: ReceiptReviewPanel } = await import("@/components/business-app/ReceiptReviewPanel");
  const base = await createFixtureBusinessDataSource().receipt("rcpt-blurry");
  assert.ok(base.record_context);
  const detail = { ...base, ...notReceipt(), ...failedRead, ...state, preparable: true, record_context: { ...base.record_context, capabilities: ["read", "prepare"] } } as ReceiptDetail;
  const prepared: string[] = [];
  const source = { ...liveBusinessDataSource, receipt: async () => detail, prepareReceipt: async (id: string) => { prepared.push(id); } };
  const page = await render(() => <BusinessConsentTestProvider accepted><ReceiptReviewPanel target={{ kind: "receipt", id: detail.id }} /></BusinessConsentTestProvider>, { source } as Partial<BusinessContextValue>);
  return { page, prepared, id: detail.id, notice: () => page.host.querySelector('[data-testid="receipt-attention"]')! };
}

test("a read that passed its deadline says the read did not finish, why, and reads again", async () => {
  const { page, prepared, id, notice } = await openRetryable({ attention: "read_deadline_passed", error_code: "document_read_deadline_passed" });
  try {
    assert.equal(notice().querySelector("h3")?.textContent, "La lectura no terminó");
    assert.match(notice().textContent ?? "", /Archivo sin leer: la lectura no estuvo disponible\. Puedes leerlo de nuevo\./);
    assert.equal(/PENDIENTE|Subir otro documento/.test(notice().textContent ?? ""), false);
    assert.ok(page.button("Leer de nuevo"));
    await page.act(async () => page.button("Leer de nuevo")!.click());
    await page.settle();
    assert.deepEqual(prepared, [id]);
  } finally {
    await page.close();
  }
});

const owner: GrantedSpace = { ...client, role: "owner", capabilities: ["read", "prepare", "approve"] };

/** A failed read opened by the owner, with the server's delete answer and a recording delete. */
async function openFailed(state: Partial<ReceiptDetail>, chosen: GrantedSpace = owner) {
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { liveBusinessDataSource } = await import("@/components/business-app/business-data");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { default: ReceiptReviewPanel } = await import("@/components/business-app/ReceiptReviewPanel");
  const base = await createFixtureBusinessDataSource().receipt("rcpt-blurry");
  const detail = { ...base, ...notReceipt(), ...failedRead, delete_available: true, ...state } as ReceiptDetail;
  const deleted: string[] = [];
  let reloads = 0;
  const source = {
    ...liveBusinessDataSource,
    receipt: async () => detail,
    receiptSource: async () => new Blob([], { type: "image/jpeg" }),
    prepareReceipt: async () => undefined,
    deleteDocument: async (id: string) => { deleted.push(id); return { document_id: id, deleted: true }; },
  };
  const page = await render(() => <BusinessConsentTestProvider accepted><ReceiptReviewPanel target={{ kind: "receipt", id: detail.id }} /></BusinessConsentTestProvider>, { source, chosen, reload: () => { reloads += 1; } } as Partial<BusinessContextValue>);
  const notice = () => page.host.querySelector('[data-testid="receipt-attention"]')!;
  return { page, deleted, id: detail.id, notice, labels: () => [...page.host.querySelectorAll('[data-testid="receipt-review-footer"] button:not([aria-label])')].map((button) => button.textContent), reloads: () => reloads };
}

for (const errorCode of ["unreadable_document", "encrypted_document"]) {
  test(`an unreadable read (${errorCode}) asks for a clearer copy and offers Eliminar documento`, async () => {
    const { page, labels, notice } = await openFailed({ attention: "unreadable", error_code: errorCode });
    try {
      assert.equal(notice().querySelector("h3")?.textContent, "No pudimos leer este archivo");
      assert.match(notice().textContent ?? "", /Archivo borroso, cortado o dañado. Sube una foto clara del recibo completo/);
      assert.equal(/No se pudo leer/.test(notice().textContent ?? ""), false, "the shared short word gives way to the step");
      assert.deepEqual(labels(), ["Subir otro documento"]);
      await page.act(async () => page.button("Subir otro documento")!.click());
      assert.deepEqual(page.uploads, ["upload"]);
    } finally {
      await page.close();
    }
  });
}

test("Eliminar documento on an unreadable read confirms, deletes it and returns to the Bandeja", async () => {
  const { page, deleted, id, reloads } = await openFailed({ attention: "unreadable", error_code: "unreadable_document" });
  try {
    const discard = page.host.querySelector<HTMLButtonElement>('[data-testid="receipt-review-footer"] button[aria-label="Eliminar documento"]');
    assert.ok(discard, "the footer offers it");
    await page.act(async () => discard.click());
    const confirm = document.querySelector<HTMLButtonElement>('[data-testid="confirm-dialog-confirm"]');
    assert.equal(confirm?.textContent, "Eliminar", "a confirm step names the delete");
    assert.deepEqual(deleted, [], "nothing leaves before the person confirms");
    await page.act(async () => confirm!.click());
    await page.settle();
    assert.deepEqual(deleted, [id]);
    assert.ok(reloads() > 0, "the Bandeja counts are read again");
    assert.deepEqual(page.opened.at(-1), { kind: "inbox" });
  } finally {
    await page.close();
  }
});

test("an unreadable read offers no Eliminar the server or the grant did not allow", async () => {
  for (const [state, chosen] of [[{ delete_available: false }, owner], [{}, client]] as const) {
    const { page, labels } = await openFailed({ attention: "unreadable", error_code: "unreadable_document", ...state }, chosen);
    try {
      assert.deepEqual(labels(), ["Subir otro documento"]);
      assert.equal(page.host.querySelector('[aria-label="Eliminar documento"]'), null);
    } finally {
      await page.close();
    }
  }
});

for (const [reason, title, body, preparable] of [
  ["ai_unavailable", "No se pudo leer", null, true],
  ["interrupted", "La lectura se detuvo", null, true],
  ["not_a_receipt", "Esto no parece un recibo", "Sube la foto o el PDF de un comprobante.", false],
  ["outcome_unknown", "No recuperamos la lectura", "Archivo sin leer: la lectura se cortó. Puedes leerlo de nuevo.", true],
  ["read_deadline_passed", "La lectura no terminó", "Archivo sin leer: la lectura no estuvo disponible. Puedes leerlo de nuevo.", true],
  ["source_unavailable", "Falta el archivo original", null, false],
] as const) {
  test(`the failed read shows the server's ${reason} and its one action`, async () => {
    const { page, notice, labels } = await openFailed({
      attention: reason, preparable, merchant: "Nombre antiguo", filename: "recibo.jpg",
      bandeja_group: { group: "attention", reason, label: "cant_read", draft_id: null, version: null },
    });
    try {
      assert.equal(page.host.querySelector("#receipt-review-title")?.textContent, "recibo.jpg");
      assert.equal(page.host.querySelector('[data-testid="status-pill"]')?.textContent, "No se pudo leer");
      assert.equal(page.host.querySelector('[data-tab="fiscal"]'), null);
      assert.equal(notice().querySelector("h3")?.textContent, title);
      if (body) assert.equal(notice().querySelector("p")?.textContent, body);
      assert.deepEqual(labels(), [preparable ? "Leer de nuevo" : "Subir otro documento"]);
      assert.equal(notice().textContent?.includes("Si reintentas, el recibo se envía"), preparable);
    } finally { await page.close(); }
  });
}

test("a daily hold uses still rows and the daily note, with only delete in its footer", async () => {
  const { page } = await openFailed({
    attention: "read_budget_day", error_code: "business_read_budget_day", preparable: true, read_pending: false,
    bandeja_group: { group: "reading", reason: "reading", label: "reading", draft_id: null, version: null },
  });
  try {
    const general = page.host.querySelector('[data-tab-panel="general"]')!;
    assert.equal(general.querySelector('[role="status"]')?.textContent, "Se lee mañana · Hoy se alcanzó el límite de lecturas.");
    assert.ok(general.textContent?.includes("Comprobante"));
    await page.act(async () => page.button("Historial")!.click());
    const events = page.host.querySelectorAll('[data-tab-panel="historial"] [data-testid="history-event"]');
    assert.equal(events.length, 1);
    assert.match(events[0].textContent ?? "", /foto-perro.jpg/);
    assert.equal(page.host.querySelector('[data-testid="status-pill"]')?.textContent, "Leyendo…");
    assert.deepEqual([...page.host.querySelectorAll('[data-testid="receipt-review-footer"] button')].map(button => button.getAttribute("aria-label")), ["Eliminar documento"]);
    assert.equal(page.host.querySelector('[data-testid="receipt-reading-band"]'), null);
  } finally { await page.close(); }
});

test("a monthly hold never says the read will happen tomorrow", async () => {
  const { page } = await openFailed({ attention: "read_budget_month", preparable: true, bandeja_group: { group: "reading", reason: "reading", label: "reading", draft_id: null, version: null } });
  try { assert.doesNotMatch(page.host.textContent ?? "", /Se lee mañana/); } finally { await page.close(); }
});

test("a read that stopped keeps its consent line and retries the same receipt", async () => {
  const { page, prepared, id, notice } = await openRetryable({ attention: "interrupted", error_code: "business_preparation_binding_missing" });
  try {
    assert.equal(notice().querySelector("h3")?.textContent, "La lectura se detuvo");
    assert.match(notice().textContent ?? "", /Si reintentas, el recibo se envía/);
    await page.act(async () => page.button("Leer de nuevo")!.click());
    await page.settle();
    assert.deepEqual(prepared, [id]);
  } finally { await page.close(); }
});
