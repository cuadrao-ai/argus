import { test, expect } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import ReceiptHistory from "@/components/business-app/ReceiptHistory";
import type { BusinessDraftRevision, BusinessDossier } from "@/lib/business-dossier";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import { dossierFixtureIds } from "@/components/business-app/dossier-fixtures";
import spanish from "@/public/locales/es-419/common.json";
import english from "@/public/locales/en/common.json";

for (const language of ["es-419", "en"] as const) test(`${language}: note changes and supporting sources use the existing immutable Activity rail`, async () => {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: language, resources: { "es-419": { translation: spanish }, en: { translation: english } }, interpolation: { escapeValue: false } });
  const facts = (await createFixtureBusinessDataSource().dossier(dossierFixtureIds.ready)).facts;
  const actor: BusinessDraftRevision["actor"] = { actor_id: "person", actor_kind: "member", display_name: "Lía", grant_id: "grant", issuer_id: "person", issuer_display_name: "Lía" };
  const revision = (version: number, extras: Partial<BusinessDraftRevision>): BusinessDraftRevision => ({ draft_id: dossierFixtureIds.ready, version, actor, before: facts, after: facts, source_ids: [], turn_key: null, created_at: `2026-10-26T12:0${version}:00Z`, ...extras });
  const history = [revision(1, { before_current_note: null, after_current_note: "Nota primera" }), revision(2, { before_current_note: "Nota primera", after_current_note: "" }), revision(3, { source_ids: ["source-original"] })];
  const sources = [{ id: "source-original", connection_id: "receipt-distinct", kind: "attachment", channel: "web", received_at: "2026-10-26T11:00:00Z", filename: "Apoyo sintético.pdf", media_type: "application/pdf" }] as BusinessDossier["sources"];
  const html = renderToStaticMarkup(<I18nextProvider i18n={i18n}><ReceiptHistory history={history} sources={sources} accounts={[]} /></I18nextProvider>);
  expect((html.match(/data-testid="receipt-history"/g) ?? []).length).toBe(1);
  expect((html.match(/data-testid="history-current-note"/g) ?? []).length).toBe(2);
  expect(html).toContain('data-testid="history-supporting"');
  expect(html).toContain("Apoyo sintético.pdf");
  expect(html).toContain("Nota primera");
  expect(html).toContain(i18n.t("business.dossier.not_recorded"));
  expect(html).not.toContain('data-approved="true"');
});
