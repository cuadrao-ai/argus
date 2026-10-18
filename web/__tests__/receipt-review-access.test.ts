import { test } from "bun:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import spanish from "@/public/locales/es-419/common.json";
import { receiptReviewAccess } from "@/components/business-app/receipt-review-access";
import PanelErrorBoundary, { PanelCrashed } from "@/components/business-app/PanelErrorBoundary";
import type { ReceiptDetail } from "@/lib/business-api";

/** The shape GET /business/receipts/{id} returns for a receipt the read left without a draft:
 *  the record context is nested, nothing about accounts or permissions sits at the top level. */
const apiDetail: ReceiptDetail = {
  id: "7c366e61-5dd7-42ff-8a58-97605f52d4b3",
  channel: "web",
  filename: "image.png",
  source_text: null,
  media_type: "image/png",
  size_bytes: 70,
  received_at: "2026-10-12T20:26:00Z",
  status: "needs_attention",
  error_code: "no_purchase_found",
  attention: "no_purchase_found",
  duplicate_of: null,
  replayed: false,
  preparable: false,
  enterable: true,
  expense_id: null,
  merchant: null,
  occurred_on: null,
  amount: null,
  currency: null,
  category_id: null,
  account_id: null,
  email_delivery_ids: [],
  email_original: false,
  record_context: { space_id: "50000000-0000-4000-8000-000000000001", space_name: "Taller", accounts: [{ id: "acct-1", nickname: "Caja", type: "cash", currency: "DOP" }], capabilities: ["read", "prepare"] },
  draft_id: null,
  version: 0,
  evidence: null,
  missing_fields: ["account_id", "amount", "currency", "occurred_on"],
};

test("the legacy review reads permissions and accounts from the nested record context", () => {
  const access = receiptReviewAccess(apiDetail);
  assert.deepEqual(access, { accounts: apiDetail.record_context?.accounts, canPrepare: true, canApprove: false });
  const owner = receiptReviewAccess({ record_context: { ...apiDetail.record_context!, capabilities: ["read", "prepare", "approve"] } });
  assert.equal(owner.canApprove, true);
});

test("a receipt without a record context is read-only, never a crash", () => {
  assert.deepEqual(receiptReviewAccess({ record_context: null }), { accounts: [], canPrepare: false, canApprove: false });
});

test("a crash inside a panel becomes the in-page message with a retry, not the page error", async () => {
  // Server rendering cannot exercise a boundary's catch, so the two halves are checked apart:
  // the boundary's state transition, and the fallback it renders in that state.
  const derived = PanelErrorBoundary.getDerivedStateFromError(new Error("render"));
  assert.equal(derived.failed, true);
  assert.match(String(derived.reference), /^c[0-9a-f]{8}$/);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const html = renderToStaticMarkup(createElement(I18nextProvider, { i18n }, createElement(PanelCrashed, { onRetry: () => undefined, reference: "c0ffee00" })));
  assert.match(html, /server-error-screen/);
  assert.match(html, /Algo salió mal de nuestro lado/);
  assert.match(html, /Intentar de nuevo/);
  assert.match(html, /Ir a Inicio/);
  assert.match(html, /admin@cuadrao.ai/);
  assert.match(html, /c0ffee00/);
  assert.equal(html.includes("render"), false);
});
