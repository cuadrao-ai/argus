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

/** A fiscal receipt whose RNC has the right length, so Aprobar goes straight to the server. */
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
    const approve = page.button("Aprobar");
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
    await page.act(async () => page.button("Aprobar")!.click());
    await page.settle();
    assert.match(page.host.querySelector('[data-testid="dossier-duplicate"]')?.textContent ?? "", /Ya registraste este comprobante\./);
    assert.equal(page.button("Ver el registrado"), undefined);
  } finally {
    await page.close();
  }
});

test("a disabled Aprobar names the missing facts beside it", async () => {
  const dossier = await createDossierFixtures(accounts).dossier(dossierFixtureIds.ready);
  dossier.approval_available = false;
  dossier.blockers = [{ code: "fact_required", field: "funding" }, { code: "fact_required", field: "business_share" }];
  serveDossier(dossier, () => Response.json(dossier));
  const { default: Review } = await import("@/components/business-app/ReceiptDossierReview");
  const page = await render(() => <Review draftId={dossier.draft_id} />);
  try {
    const approve = page.button("Aprobar");
    assert.ok(approve);
    assert.equal(approve.disabled, true);
    const reason = page.host.querySelector('[data-testid="approve-reason"]');
    assert.equal(reason?.textContent, "Falta: Cómo se pagó, Parte del negocio");
    // The footer says what is left on its left and holds the actions on its right.
    assert.ok(reason?.closest('[data-testid="receipt-review-footer"]') && reason.closest('[data-testid="receipt-review-footer"]') === approve.closest('[data-testid="receipt-review-footer"]'), "the reason sits in the footer with the button");
    assert.equal(approve.getAttribute("aria-describedby"), reason?.id);
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

test("a client's record for a file that is not a receipt says so and offers Subir otro archivo first, then Escribir datos", async () => {
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
    assert.equal(notice?.querySelector(".font-medium")?.textContent, "Esto no parece un recibo.");
    assert.equal(notice?.textContent?.includes("borroso"), false);
    const labels = [...notice!.querySelectorAll("button")].map((button) => button.textContent);
    assert.deepEqual(labels, ["Subir otro archivo", "Escribir datos"], "a prepare grant can upload another file, and upload comes first");
    await page.act(async () => page.button("Subir otro archivo")!.click());
    assert.deepEqual(page.uploads, ["upload"]);
  } finally {
    await page.close();
  }
});
