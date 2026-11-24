import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { BusinessDossier } from "@/lib/business-dossier";
import type { ReceiptDetail } from "@/lib/business-api";
import { dossierFixtureIds } from "@/components/business-app/dossier-fixtures";

mock.module("next/navigation", () => ({
  usePathname: () => "/biz",
  useRouter: () => ({ push: () => {}, replace: () => {}, refresh: () => {}, prefetch: () => {} }),
  useSearchParams: () => new URLSearchParams(),
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

type Change = (dossier: BusinessDossier) => void;

/** Ferretería La Esquina opened as a prepared record; the change edits the record the server returns. */
async function mount({ change, overrides = {}, receipt = {}, until = "footer" }: { change?: Change; overrides?: Partial<BusinessDataSource>; receipt?: Partial<ReceiptDetail>; until?: "footer" | "title" } = {}) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
  const ReceiptReviewPanel = (await import("@/components/business-app/ReceiptReviewPanel")).default;
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  const source: BusinessDataSource = {
    ...fixture,
    receipt: async (id, signal) => ({ ...await fixture.receipt(id, signal), draft_id: dossierFixtureIds.fiscal, ...receipt }),
    dossier: async (id) => {
      const dossier = structuredClone(await fixture.dossier(id));
      change?.(dossier);
      return dossier;
    },
    ...overrides,
  };
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source}>
            <ReceiptReviewPanel target={{ kind: "receipt", id: "rcpt-ferreteria" }} />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  const settle = async (ready: () => boolean) => {
    for (let i = 0; i < 80 && !ready(); i += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    assert.ok(ready(), "the page settled");
  };
  const footer = () => host.querySelector<HTMLElement>('[data-testid="receipt-review-footer"]');
  const button = (name: string) => [...(footer()?.querySelectorAll<HTMLButtonElement>("button") ?? [])].find((item) => item.textContent === name);
  await settle(() => Boolean(until === "title" ? host.querySelector("#receipt-review-title") : footer()));
  return { host, act, settle, footer, button, close: () => act(async () => { root.unmount(); host.remove(); }) };
}

const LISTO = { group: "listo", reason: null, label: "ready", draft_id: null, version: null } as const;
const ACCEPTED = { group: null, reason: null, label: "accepted", draft_id: null, version: null } as const;

const noDate: Change = (dossier) => {
  dossier.facts.occurred_on = { state: "unknown", value: null, origin: null, verified: false, source_ids: [] };
  dossier.blockers = [{ code: "fact_required", field: "occurred_on" }];
  dossier.bandeja_group = { group: "attention", reason: "missing_date", label: "needs_attention" };
  dossier.listo_gaps = ["missing_date"];
  dossier.reasons = { missing_date: { field: "occurred_on", words: "business.transactions.layout.workflow.missing.missing_date" } };
  dossier.approval_available = false;
};

describe("the receipt detail's header", () => {
  test("the supplier is the title and the status comes under it, with no business name or revision number", async () => {
    const page = await mount({ receipt: { bandeja_group: LISTO } });
    assert.equal(page.host.querySelector("#receipt-review-title")?.textContent, "Ferretería La Esquina");
    const status = page.host.querySelector('[data-testid="dossier-status"]')!;
    assert.equal(status.querySelector('[data-testid="status-pill"]')?.textContent, "Listo para aceptar");
    assert.doesNotMatch(status.textContent ?? "", /Revisión|Mi negocio/);
    const review = page.host.querySelector('[data-testid="business-record-review"]')!;
    assert.ok(review.textContent!.indexOf("Ferretería La Esquina") < review.textContent!.indexOf("Fecha"));
    await page.close();
  });

  test("the status word is the list's, and an accepted receipt has no pill", async () => {
    for (const draft_id of [dossierFixtureIds.fiscal, null]) {
      for (const [status, bandeja_group, word] of [["review_ready", LISTO, "Listo para aceptar"], ["confirmed", ACCEPTED, null]] as const) {
        const change: Change = (dossier) => { dossier.bandeja_group = { group: bandeja_group.group, reason: null, label: bandeja_group.label }; dossier.listo_gaps = []; };
        const page = await mount({ receipt: { status, bandeja_group, draft_id }, change, until: "title" });
        assert.equal(page.host.querySelector('[data-testid="status-pill"]')?.textContent ?? null, word, `${status} ${draft_id ? "with" : "without"} a draft`);
        await page.close();
      }
    }
  });

  test("an unknown total reads Sin dato, never zero", async () => {
    const page = await mount({ change: (dossier) => { dossier.facts.amount = { state: "unknown", value: null, origin: null, verified: false, source_ids: [] }; } });
    const total = page.host.querySelector('[data-fact="amount"] [data-row-value]');
    assert.equal(total?.textContent, "Sin dato");
    assert.equal(total?.getAttribute("data-empty"), "true");
    assert.doesNotMatch(page.host.querySelector('[data-testid="receipt-facts-montos"]')?.textContent ?? "", /0\.00|desconocido/i);
    await page.close();
  });
});

describe("a record opened without its receipt", () => {
  test("a record still being accepted says its outcome is not known yet; an open one does not", async () => {
    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const i18next = (await import("i18next")).default;
    const { I18nextProvider } = await import("react-i18next");
    const spanish = (await import("@/public/locales/es-419/common.json")).default;
    const { BusinessWorkspaceProvider } = await import("@/components/business-app/BusinessWorkspace");
    const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
    const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
    const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
    const ReceiptReviewPanel = (await import("@/components/business-app/ReceiptReviewPanel")).default;
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
    const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
    for (const state of ["open", "accepting"] as const) {
      const source: BusinessDataSource = { ...fixture, dossier: async (id) => ({ ...structuredClone(await fixture.dossier(id)), review_state: state }) };
      const host = document.createElement("div");
      document.body.appendChild(host);
      const root = createRoot(host);
      await act(async () => {
        root.render(<I18nextProvider i18n={i18n}><BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={source}><ReceiptReviewPanel target={{ kind: "draft", id: dossierFixtureIds.ready }} /></BusinessWorkspaceProvider></BusinessConsentTestProvider></I18nextProvider>);
      });
      for (let i = 0; i < 80 && !host.querySelector('[data-testid="receipt-review-footer"]'); i += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
      const unknown = [...host.querySelectorAll('[role="status"]')].some((item) => item.textContent?.includes("Todavía no se conoce el resultado de la acción."));
      assert.equal(unknown, state === "accepting", `${state}: ${host.textContent?.slice(0, 300)}`);
      assert.equal(Boolean([...host.querySelectorAll("button")].find((item) => item.textContent === "Consultar registro actual")), state === "accepting", `${state}: the way to check`);
      await act(async () => { root.unmount(); host.remove(); });
    }
  });
});

describe("the footer", () => {
  test("holds Más and the one Aceptar for a record opened with no list, and nothing else, with no reason while Aceptar is open", async () => {
    const page = await mount();
    const footer = page.footer()!;
    // Más holds the Personal mark, the note and the refresh; only its trigger sits in the footer row.
    assert.deepEqual([...footer.querySelectorAll("button")].filter((item) => !item.closest("#receipt-more-panel")).map((item) => item.textContent), ["Más", "Aceptar"]);
    assert.equal(page.button("Aceptar")?.disabled, false);
    assert.equal(footer.querySelector('[data-testid="approve-reason"]'), null);
    await page.close();
  });

  test("a missing date disables Aceptar, and the header reason alone says why", async () => {
    const page = await mount({ change: noDate });
    assert.equal(page.button("Aceptar")?.disabled, true);
    assert.equal(page.footer()!.querySelector('[data-testid="approve-reason"]'), null, "the footer repeats nothing");
    assert.equal(page.host.querySelector('[data-testid="dossier-reason"]')?.textContent, "Falta la fecha");
    const row = page.host.querySelector('[data-fact="occurred_on"]')!;
    assert.equal(row.querySelector('[data-testid="row-status-occurred_on"]')?.getAttribute("data-status"), "warn", "the row marks where");
    assert.equal(row.textContent?.includes("Agrega la fecha para aceptar"), false, "and adds no sentence of its own");
    await page.close();
  });

  test("approving shows a spinner on Aceptar and a second press sends nothing", async () => {
    let release: () => void = () => {};
    let approvals = 0;
    const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
    const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
    const page = await mount({
      change: (dossier) => {
        if (dossier.facts.fiscal) dossier.facts.fiscal.rnc = { state: "known", value: "101123456", origin: "owner_stated", verified: false, source_ids: [] };
      },
      overrides: {
        approveDraft: async (id, version) => {
          approvals += 1;
          await new Promise<void>((resolve) => { release = resolve; });
          return { ...await fixture.dossier(id), version, inbox_counts: (await fixture.receiptPage!("inbox")).activity };
        },
      },
    });
    const approve = page.button("Aceptar")!;
    await page.act(async () => { approve.click(); });
    const busy = page.footer()!.querySelector<HTMLButtonElement>('button[aria-busy="true"]')!;
    assert.ok(busy.querySelector(".animate-spin"), "the spinner shows");
    assert.equal(busy.textContent, "Aceptando…");
    assert.equal(busy.disabled, true);
    await page.act(async () => { busy.click(); });
    assert.equal(approvals, 1);
    assert.equal(page.footer()!.querySelector('[data-testid="approve-reason"]'), null, "no reason while the approval runs");
    await page.act(async () => { release(); });
    await page.close();
  });
});

describe("a receipt that will not load", () => {
  test("says so in red beside an alert icon, and Reintentar asks again", async () => {
    let calls = 0;
    const { act } = await import("react");
    const { createRoot } = await import("react-dom/client");
    const i18next = (await import("i18next")).default;
    const { I18nextProvider } = await import("react-i18next");
    const spanish = (await import("@/public/locales/es-419/common.json")).default;
    const { BusinessWorkspaceProvider } = await import("@/components/business-app/BusinessWorkspace");
    const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
    const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
    const ReceiptReviewPanel = (await import("@/components/business-app/ReceiptReviewPanel")).default;
    const i18n = i18next.createInstance();
    await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
    const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
    const source: BusinessDataSource = {
      ...fixture,
      receipt: async (id, signal) => {
        calls += 1;
        if (calls === 1) throw Object.assign(new Error("down"), { status: 500 });
        return fixture.receipt(id, signal);
      },
    };
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(<I18nextProvider i18n={i18n}><BusinessConsentTestProvider accepted><BusinessWorkspaceProvider source={source}><ReceiptReviewPanel target={{ kind: "receipt", id: "rcpt-ferreteria" }} /></BusinessWorkspaceProvider></BusinessConsentTestProvider></I18nextProvider>);
    });
    for (let i = 0; i < 40 && !host.querySelector('[data-testid="receipt-load-error"]'); i += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    const error = host.querySelector('[data-testid="receipt-load-error"]')!;
    const alert = error.querySelector('[role="alert"]')!;
    assert.equal(alert.textContent, "No pudimos actualizar.");
    assert.match(alert.className, /text-\[#9e2f39\]/);
    assert.ok(alert.querySelector(".lucide-circle-alert"));
    const retry = [...error.querySelectorAll("button")].find((item) => item.textContent === "Reintentar")!;
    await act(async () => { retry.click(); });
    for (let i = 0; i < 80 && !host.querySelector("#receipt-review-title"); i += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    assert.equal(calls, 2);
    assert.ok(host.querySelector("#receipt-review-title"));
    await act(async () => { root.unmount(); host.remove(); });
  });
});
