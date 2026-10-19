import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessDataSource } from "@/components/business-app/business-data";
import type { BusinessDossier } from "@/lib/business-dossier";

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
async function mount({ change, overrides = {} }: { change?: Change; overrides?: Partial<BusinessDataSource> } = {}) {
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
    receipt: async (id, signal) => ({ ...await fixture.receipt(id, signal), draft_id: dossierFixtureIds.fiscal }),
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
  await settle(() => Boolean(footer()));
  return { host, act, settle, footer, button, close: () => act(async () => { root.unmount(); host.remove(); }) };
}

const noDate: Change = (dossier) => {
  dossier.facts.occurred_on = { state: "unknown", value: null, origin: null, verified: false, source_ids: [] };
  dossier.blockers = [{ code: "fact_required", field: "occurred_on" }];
  dossier.approval_available = false;
};

describe("the receipt detail's top block", () => {
  test("supplier, total and status come first, with no business name or revision number", async () => {
    const page = await mount();
    const top = page.host.querySelector('[data-testid="receipt-top-block"]')!;
    assert.equal(top.querySelector("h2")?.textContent, "Ferretería La Esquina");
    assert.match(top.querySelector('[data-testid="receipt-total"]')?.textContent ?? "", /^RD\$ \d{1,3}(,\d{3})*\.\d{2}$/);
    assert.equal(top.querySelector('[data-testid="status-pill"]')?.textContent, "Pendiente");
    assert.doesNotMatch(top.textContent ?? "", /Revisión|Mi negocio/);
    const review = page.host.querySelector('[data-testid="business-record-review"]')!;
    assert.ok(review.textContent!.indexOf("Ferretería La Esquina") < review.textContent!.indexOf("Fecha de actividad"));
    await page.close();
  });

  test("an unknown total is hidden, never shown as zero", async () => {
    const page = await mount({ change: (dossier) => { dossier.facts.amount = { state: "unknown", value: null, origin: null, verified: false, source_ids: [] }; } });
    assert.equal(page.host.querySelector('[data-testid="receipt-total"]'), null);
    assert.doesNotMatch(page.host.querySelector('[data-testid="receipt-top-block"]')?.textContent ?? "", /0\.00|desconocido/i);
    await page.close();
  });
});

describe("the footer", () => {
  test("holds Aprobar and Aprobar y siguiente, and nothing else, with no reason while Aprobar is open", async () => {
    const page = await mount();
    const footer = page.footer()!;
    assert.deepEqual([...footer.querySelectorAll("button")].map((item) => item.textContent), ["Aprobar", "Aprobar y siguiente"]);
    assert.equal(page.button("Aprobar")?.disabled, false);
    assert.equal(footer.querySelector('[data-testid="approve-reason"]'), null);
    await page.close();
  });

  test("a missing date disables Aprobar with Agrega la fecha para aprobar beside it", async () => {
    const page = await mount({ change: noDate });
    assert.equal(page.button("Aprobar")?.disabled, true);
    assert.equal(page.button("Aprobar y siguiente")?.disabled, true);
    assert.equal(page.footer()!.querySelector('[data-testid="approve-reason"]')?.textContent, "Agrega la fecha para aprobar");
    await page.close();
  });

  test("any other blocker keeps today's reason, and a record with no blocker still says why", async () => {
    for (const [blockers, reason] of [
      [[{ code: "unknown_funding", field: "funding" }], "Confirma cómo se pagó."],
      [[], "Este registro necesita más revisión antes de aprobarse."],
    ] as const) {
      const page = await mount({ change: (dossier) => { dossier.blockers = [...blockers]; dossier.approval_available = false; } });
      assert.equal(page.button("Aprobar")?.disabled, true);
      assert.equal(page.footer()!.querySelector('[data-testid="approve-reason"]')?.textContent, reason);
      await page.close();
    }
  });

  test("approving shows a spinner on Aprobar and a second press sends nothing", async () => {
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
          return fixture.dossier(id).then((dossier) => ({ ...dossier, version }));
        },
      },
    });
    const approve = page.button("Aprobar")!;
    await page.act(async () => { approve.click(); });
    const busy = page.footer()!.querySelector<HTMLButtonElement>('button[aria-busy="true"]')!;
    assert.ok(busy.querySelector(".animate-spin"), "the spinner shows");
    assert.equal(busy.textContent, "Aprobando…");
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
        if (calls === 1) throw Object.assign(new Error("gone"), { status: 404 });
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
    assert.equal(alert.textContent, "Este recibo no está disponible. Puede que lo hayan quitado.");
    assert.match(alert.className, /text-\[#9e2f39\]/);
    assert.ok(alert.querySelector(".lucide-circle-alert"));
    const retry = [...error.querySelectorAll("button")].find((item) => item.textContent === "Reintentar")!;
    await act(async () => { retry.click(); });
    for (let i = 0; i < 80 && !host.querySelector('[data-testid="receipt-top-block"]'); i += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    assert.equal(calls, 2);
    assert.ok(host.querySelector('[data-testid="receipt-top-block"]'));
    await act(async () => { root.unmount(); host.remove(); });
  });
});
