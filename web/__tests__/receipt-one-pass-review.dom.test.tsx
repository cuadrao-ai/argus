import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReceiptDetail } from "@/lib/business-api";
import type { BusinessDataSource } from "@/components/business-app/business-data";

mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

async function mount(overrides: (fixture: BusinessDataSource) => Partial<BusinessDataSource> = () => ({})) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const english = (await import("@/public/locales/en/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const BusinessPanel = (await import("@/components/business-app/BusinessPanel")).default;
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish }, en: { translation: english } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: true });
  // The email's own document stands in for a receipt saved with reading off.
  const source = {
    ...fixture,
    receipt: async (id: string, signal?: AbortSignal): Promise<ReceiptDetail> => {
      const found = await fixture.receipt(id, signal);
      return id === "rcpt-saved" ? { ...found, email_original: false, activity: { state: "saved_unread", unread: true, completion_cursor: null } } : found;
    },
    ...overrides(fixture),
  };
  let api: ReturnType<typeof useBusiness> | null = null;
  function Probe() {
    api = useBusiness();
    return <BusinessPanel />;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessWorkspaceProvider source={source as never}>
          <Probe />
        </BusinessWorkspaceProvider>
      </I18nextProvider>,
    );
  });
  const wait = async (done: () => boolean) => {
    for (let i = 0; i < 80; i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
      if (done()) return;
    }
    throw new Error(`timed out: ${host.textContent?.slice(0, 300)}`);
  };
  const open = async (panel: Parameters<ReturnType<typeof useBusiness>["openPanel"]>[0], ready: () => boolean) => {
    await act(async () => api!.openPanel(panel));
    await wait(ready);
  };
  const pages = () => host.querySelectorAll('[data-testid="business-record-review"]');
  const frame = () => {
    const [page] = pages();
    return {
      count: pages().length,
      source: page?.querySelector('[data-testid="receipt-review-source"]') ?? null,
      fields: page?.querySelector('[data-testid="receipt-review-fields"]') ?? null,
      title: page?.querySelector("#receipt-review-title")?.textContent ?? null,
    };
  };
  return { act, root, host, wait, open, frame, source, i18n, api: () => api! };
}

function button(host: Element, text: string) {
  const found = [...host.querySelectorAll<HTMLButtonElement>("button")].find((item) => item.textContent === text);
  assert.ok(found, `missing button ${text}`);
  return found;
}

async function setup(capabilities: ("read" | "prepare" | "approve")[] = ["read", "prepare", "approve"], uncertainSave = false) {
  const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
  const { extractedConfirmationPatch } = await import("@/components/business-app/receipt-fact-rows");
  const id = dossierFixtureIds.ready;
  let current: Awaited<ReturnType<BusinessDataSource["dossier"]>>;
  const saved: unknown[] = [];
  let approvals = 0;
  const page = await mount((fixture) => ({
    dossier: async () => {
      if (!current) {
        current = structuredClone(await fixture.dossier(id));
        current.capabilities = capabilities;
        current.facts.counterparty = { ...current.facts.counterparty, origin: "extracted", verified: false } as typeof current.facts.counterparty;
        current.facts.amount = { ...current.facts.amount, origin: "extracted", verified: false } as typeof current.facts.amount;
        current.facts.occurred_on = { state: "unknown", value: null, origin: null, verified: false, source_ids: [] };
        current.blockers = [{ code: "missing_fields", field: "occurred_on" }];
        current.questions = [];
        current.approval_available = false;
      }
      return structuredClone(current);
    },
    reviewDraft: async (_id, version, facts) => {
      if (uncertainSave) throw new Error("transport outcome unknown");
      assert.ok(capabilities.includes("prepare"));
      assert.equal(version, current.version);
      saved.push(structuredClone(facts));
      for (const [key, value] of Object.entries(facts)) Object.assign(current.facts, { [key]: { ...value, origin: "member_set", verified: false, source_ids: [] } });
      current.version += 1;
      if (current.facts.occurred_on.state === "known") { current.blockers = []; current.approval_available = true; }
      return structuredClone(current);
    },
    approveDraft: async () => { approvals += 1; throw new Error("probe records the separate approval call"); },
  }));
  await page.open({ kind: "draft", draftId: id }, () => Boolean(page.host.querySelector('[data-testid="receipt-current-facts"]')));
  return { ...page, saved, approvals: () => approvals, current: () => current, confirmations: () => extractedConfirmationPatch(current, {}) };
}

async function fill(page: Awaited<ReturnType<typeof setup>>, selector: string, value: string) {
  const input = page.host.querySelector<HTMLInputElement>(selector);
  assert.ok(input, selector);
  await page.act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

describe("one-pass receipt review", () => {
  test("receipt copy follows the selected language and keeps canonical labels on other surfaces", async () => {
    const page = await setup();
    try {
      const count = Object.keys(page.confirmations()).length;
      assert.ok(button(page.host, `Confirmar ${count} datos leídos`));
      assert.ok(button(page.host, "Aprobar"));
      assert.ok(page.host.textContent?.includes("Leído del recibo"));
      assert.ok(page.host.textContent?.includes("Agrega la fecha para aprobar"));
      assert.equal(page.i18n.t("business.dossier.approve"), "Aprobar gasto");
      assert.equal(page.i18n.t("business.dossier.confirm_value"), "Confirmar");
      await page.act(async () => { await page.i18n.changeLanguage("en"); });
      assert.ok(button(page.host, `Confirm ${count}`));
      assert.ok(button(page.host, "Approve expense"));
      assert.ok(page.host.textContent?.includes("Read from source · not verified"));
      assert.ok(page.host.textContent?.includes("Needs a decision before approval"));
      for (const copy of ["Leído del recibo", "Agrega la fecha para aprobar", "datos leídos"]) assert.ok(!page.host.textContent?.includes(copy));
      await page.act(async () => { await page.i18n.changeLanguage("es-419"); });
      assert.ok(button(page.host, `Confirmar ${count} datos leídos`));
      assert.ok(button(page.host, "Aprobar"));
      assert.ok(page.host.textContent?.includes("Leído del recibo"));
      assert.ok(page.host.textContent?.includes("Agrega la fecha para aprobar"));
      assert.equal(page.saved.length, 0);
      assert.equal(page.approvals(), 0);
    } finally { await page.act(async () => page.root.unmount()); }
  });

  test("confirmation preserves edited and missing values, hides at zero, and never approves", async () => {
    const page = await setup();
    try {
      assert.equal(page.host.querySelector('[data-testid="receipt-current-facts"] dl > div')?.getAttribute("data-fact"), "occurred_on");
      assert.equal(page.host.querySelector<HTMLInputElement>('[placeholder="dd/mm/aaaa"]')?.value, "");
      assert.ok(page.host.textContent?.includes("Agrega la fecha para aprobar"));
      assert.ok(page.host.textContent?.includes("Leído del recibo"));
      assert.equal(page.host.querySelectorAll(".lucide-sparkles").length, 0);
      await page.act(async () => (page.host.querySelector('[data-fact="amount"] button') as HTMLButtonElement).click());
      assert.equal(document.activeElement, page.host.querySelector('[data-testid="dossier-review-amount"]'));
      await fill(page, '[data-testid="dossier-review-amount"]', "950");
      const count = Object.keys(page.confirmations()).length - 1;
      await page.act(async () => button(page.host, `Confirmar ${count} datos leídos`).click());
      assert.ok(page.saved.length === 1);
      assert.equal(Object.hasOwn(page.saved[0] as object, "amount"), false);
      assert.equal(Object.hasOwn(page.saved[0] as object, "occurred_on"), false);
      assert.equal(page.host.querySelector<HTMLInputElement>('[data-testid="dossier-review-amount"]')?.value, "950");
      assert.equal(page.current().facts.occurred_on.state, "unknown");
      assert.equal(page.approvals(), 0);
      assert.equal(button(page.host, "Aprobar").disabled, true);
      assert.ok(!page.host.textContent?.includes("Confirmar 0 datos leídos"));
      assert.ok(![...page.host.querySelectorAll("button")].some((item) => item.textContent?.startsWith("Confirmar ")));
      await fill(page, '[placeholder="dd/mm/aaaa"]', "31/02/2026");
      assert.equal(button(page.host, "Guardar detalles de revisión").disabled, true);
      await fill(page, '[placeholder="dd/mm/aaaa"]', "16/10/2026");
      await page.act(async () => button(page.host, "Guardar detalles de revisión").click());
      assert.equal(page.current().facts.occurred_on.value, "2026-10-16");
      assert.equal(page.approvals(), 0);
      assert.equal(button(page.host, "Aprobar").disabled, false);
      await page.act(async () => button(page.host, "Aprobar").click());
      assert.equal(page.approvals(), 1);
    } finally { await page.act(async () => page.root.unmount()); }
  });

  test("an uncertain save retains edits and pauses all writes after refresh", async () => {
    const page = await setup(["read", "prepare", "approve"], true);
    try {
      await page.act(async () => (page.host.querySelector('[data-fact="amount"] button') as HTMLButtonElement).click());
      await fill(page, '[data-testid="dossier-review-amount"]', "950");
      await page.act(async () => button(page.host, "Guardar detalles de revisión").click());
      await page.act(async () => button(page.host, "Consultar registro actual").click());
      assert.equal(page.host.querySelector<HTMLInputElement>('[data-testid="dossier-review-amount"]')?.value, "950");
      assert.equal(button(page.host, "Guardar detalles de revisión").disabled, true);
      assert.equal(button(page.host, "Aprobar").disabled, true);
      assert.equal(page.approvals(), 0);
      assert.equal(page.saved.length, 0);
    } finally { await page.act(async () => page.root.unmount()); }
  });

  test("prepare-only access has the locked line and no approval; read-only has no edit or confirm", async () => {
    for (const capabilities of [["read", "prepare"], ["read"]] as const) {
      const page = await setup([...capabilities]);
      try {
        assert.equal(page.host.textContent?.includes("Puedes revisar y preparar este recibo. El dueño lo aprueba."), capabilities.length === 2);
        assert.equal(page.host.querySelector('[data-testid="receipt-review-footer"]'), null);
        if (capabilities.length === 1) {
          assert.equal(page.host.querySelector('[data-fact="amount"] button'), null);
          assert.equal(page.host.querySelector<HTMLInputElement>('[placeholder="dd/mm/aaaa"]')?.value, "");
          assert.equal(page.host.querySelector<HTMLInputElement>('[placeholder="dd/mm/aaaa"]')?.disabled, true);
          assert.ok(![...page.host.querySelectorAll("button")].some((item) => item.textContent?.startsWith("Confirmar ")));
        }
        assert.equal(page.approvals(), 0);
      } finally { await page.act(async () => page.root.unmount()); }
    }
  });
});
