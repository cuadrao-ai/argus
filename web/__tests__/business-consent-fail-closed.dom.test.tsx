import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import { periodRange } from "@/components/business-app/business-format";
import BusinessInboxPanel from "@/components/business-app/BusinessInboxPanel";
import ReceiptReadingControl from "@/components/business-app/ReceiptReadingControl";
import ReceiptReviewPanel from "@/components/business-app/ReceiptReviewPanel";
import { useBusinessActions } from "@/components/business-app/business-actions";
import { BusinessConsentTestProvider } from "@/components/business-app/business-consent-context";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { ReceiptDetail, ReceiptSummary } from "@/lib/business-api";
import english from "@/public/locales/en/common.json";

const i18n = i18next.createInstance();

beforeAll(async () => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
  await i18n.init({ lng: "en", resources: { en: { translation: english } } });
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

function context(source: BusinessDataSource, inbox: ReceiptSummary[] = []): BusinessContextValue {
  return {
    source,
    records: { workspace: null, overview: null, inbox, notes: [], notesError: false, notesTruncated: false, error: false },
    spaces: [],
    chosen: { space_id: "own", grant_id: "own", name: "Colmado", role: "owner", capabilities: ["prepare", "approve"], access_seen: true },
    chooseBusiness: () => {},
    markAccessSeen: async () => {},
    lostAccess: false,
    revision: 0,
    reload: () => {},
    period: periodRange("this_month"),
    setPeriod: () => {},
    panel: { kind: "inbox" },
    openPanel: () => {},
    actions: { create: [], composer: [], starterEntries: [] },
    bridge: null,
    attachedReceipt: null,
    clearAttachedReceipt: () => {},
  } as BusinessContextValue;
}

function Starters() {
  const actions = useBusinessActions({
    records: {
      workspace: { chat_available: true, assistant_available: true } as BusinessContextValue["records"]["workspace"],
      overview: { totals: [{ count: 3, currency: "DOP", amount: "10.00" }] } as BusinessContextValue["records"]["overview"],
      inbox: [],
    },
    bridge: { prepareQuestion: () => {} },
    openIntake: () => {},
    openRecordExpense: () => {},
    openCapture: () => {},
    openPanel: () => {},
  });
  return (
    <div>
      {actions.starterEntries.map((entry) => (
        <button key={entry.key} type="button">{entry.label}</button>
      ))}
    </div>
  );
}

const inboxReceipt = {
  id: "rcpt-1",
  channel: "web",
  filename: "recibo.pdf",
  source_text: null,
  media_type: "application/pdf",
  size_bytes: 70,
  received_at: "2026-10-13T17:14:00Z",
  status: "needs_attention",
  error_code: null,
  attention: "amount_unclear",
  duplicate_of: null,
  replayed: false,
  preparable: true,
  enterable: false,
  read_pending: false,
  expense_id: null,
  merchant: "Ferretería",
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
} as unknown as ReceiptSummary;

test("without a consent provider, model actions stay blocked and manual recording stays available", async () => {
  const calls = { reading: 0, enable: 0, prepare: 0, rebind: 0 };
  const fixture = createFixtureBusinessDataSource();
  const rows = await fixture.receipts("inbox");
  const base = await fixture.receipt(rows[0].id);
  const detail = {
    ...base,
    id: "rcpt-1",
    status: "needs_attention",
    preparable: true,
    enterable: false,
    draft_id: null,
    read_pending: false,
    error_code: "business_record_not_found",
    attention: "amount_unclear",
    activity: null,
    record_context: base.record_context
      ? { ...base.record_context, capabilities: ["prepare", "approve"] }
      : base.record_context,
  } as ReceiptDetail;
  const source: BusinessDataSource = {
    ...fixture,
    receiptReading: async () => { calls.reading += 1; return { scope_version: 1, enabled: false, available: true, can_change: true, disclosure: "Shown only when accepted.", disclosure_token: "a".repeat(64), route: null, consented_at: null, revoked_at: null }; },
    setReceiptReading: async (reading) => { calls.enable += 1; return { ...reading, enabled: true }; },
    receipt: async () => detail,
    prepareReceipt: async () => { calls.prepare += 1; },
    rebindReceipt: async () => { calls.rebind += 1; return detail; },
    emailIntake: async () => ({ enabled: false, receiving_address: null }),
    emailDeliveries: async () => [],
  };
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const tree = (node: ReactNode, inbox: ReceiptSummary[] = []) => (
    <I18nextProvider i18n={i18n}>
      <BusinessContext.Provider value={context(source, inbox)}>{node}</BusinessContext.Provider>
    </I18nextProvider>
  );
  await act(async () => { root.render(tree(<><Starters /><ReceiptReadingControl /><BusinessInboxPanel /></>, [inboxReceipt])); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  const labels = [...host.querySelectorAll("button")].map((button) => button.textContent);
  assert.equal(labels.includes("Add"), true);
  assert.equal(labels.includes("What did I spend this month?"), false);
  assert.equal(host.querySelector('[data-testid="receipt-reading-control"]'), null);
  assert.equal(calls.enable, 0);
  const retry = [...host.querySelectorAll("button")].find((button) => button.textContent === "Retry");
  assert.ok(retry);
  await act(async () => { retry.click(); });
  await act(async () => { await Promise.resolve(); });
  assert.equal(calls.prepare, 0);
  assert.equal(host.textContent?.includes("Ferretería"), true);

  await act(async () => { root.render(tree(<ReceiptReviewPanel target={{ kind: "receipt", id: "rcpt-1" }} />)); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  const rebind = host.querySelector('[data-testid="receipt-rebind"]') as HTMLButtonElement | null;
  const prepare = [...host.querySelectorAll("button")].find((button) => button.textContent?.includes("Try again with AI"));
  assert.ok(rebind);
  assert.ok(prepare);
  await act(async () => { rebind.click(); prepare.click(); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  assert.equal(calls.rebind, 0);
  assert.equal(calls.prepare, 0);
  assert.equal(host.textContent?.includes("Bind to my current access"), true);

  calls.reading = 0;
  calls.enable = 0;
  calls.prepare = 0;
  calls.rebind = 0;
  const open = (node: ReactNode, inbox: ReceiptSummary[] = []) => tree(<BusinessConsentTestProvider accepted>{node}</BusinessConsentTestProvider>, inbox);
  await act(async () => { root.render(open(<><Starters /><ReceiptReadingControl /><BusinessInboxPanel /></>, [inboxReceipt])); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  const openLabels = [...host.querySelectorAll("button")].map((button) => button.textContent);
  assert.equal(openLabels.includes("What did I spend this month?"), true);
  assert.equal(host.querySelector('[data-testid="receipt-reading-control"]')?.textContent?.includes("Turn receipt reading on"), true);
  const openRetry = [...host.querySelectorAll("button")].find((button) => button.textContent === "Retry");
  assert.ok(openRetry);
  await act(async () => { openRetry.click(); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  assert.equal(calls.prepare, 1);
  calls.prepare = 0;
  await act(async () => { root.render(open(<ReceiptReviewPanel target={{ kind: "receipt", id: "rcpt-1" }} />)); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  const openPrepare = [...host.querySelectorAll("button")].find((button) => button.textContent?.includes("Try again with AI")) as HTMLButtonElement;
  assert.ok(openPrepare);
  await act(async () => { openPrepare.click(); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  assert.equal(calls.prepare, 1);
  const openRebind = host.querySelector('[data-testid="receipt-rebind"]') as HTMLButtonElement;
  await act(async () => { openRebind.click(); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  assert.equal(calls.rebind, 1);
  assert.equal(calls.prepare, 2);

  await act(async () => root.unmount());
  host.remove();
});
