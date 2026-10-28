import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessDossier } from "@/lib/business-dossier";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

type Mode = "success" | "error" | "stale" | "hold";
async function mount(mode: Mode = "success", options: { readOnly?: boolean; closed?: boolean; noCandidates?: boolean; externalBusy?: boolean } = {}) {
  const { act, useState } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { ReceiptDuplicateResolution } = await import("@/components/business-app/ReceiptDossierReview");
  const DossierAttentionStrip = (await import("@/components/business-app/DossierAttentionStrip")).default;
  const { dossierAttention } = await import("@/components/business-app/dossier-attention");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
  const fixture = await createFixtureBusinessDataSource().dossier(dossierFixtureIds.ready);
  const initial: BusinessDossier = {
    ...fixture, draft_id: "draft-new", version: 7,
    review_state: options.closed ? "accepted" : "open",
    capabilities: options.readOnly ? ["read"] : ["read", "prepare"],
    blockers: [{ code: "possible_duplicate", field: null }, { code: "fact_required", field: "funding" }],
    approval_available: false,
    duplicate_candidates: options.noCandidates ? [] : [{ draft_id: "draft-original", version: 3 }],
  };
  const next: BusinessDossier = { ...initial, version: 8, blockers: [{ code: "fact_required", field: "funding" }], duplicate_candidates: [] };
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const requests: { url: string; options?: RequestInit }[] = [];
  const opened: string[] = [];
  const oldFetch = globalThis.fetch;
  let release = () => {};
  const hold = new Promise<void>((resolve) => { release = resolve; });
  const fetcher = async (input: RequestInfo | URL, init?: RequestInit) => {
    requests.push({ url: String(input), options: init });
    if (mode === "hold") await hold;
    if (mode === "error") throw new Error("Synthetic offline transport");
    return new Response(JSON.stringify(mode === "stale" ? { code: "stale_version" } : next), { status: mode === "stale" ? 409 : 200, headers: { "Content-Type": "application/json" } });
  };
  globalThis.fetch = fetcher;
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  function View() {
    const [dossier, setDossier] = useState(initial);
    const [busy, setBusy] = useState(false);
    return <I18nextProvider i18n={i18n}>
      <DossierAttentionStrip items={dossierAttention(dossier, [], i18n.t.bind(i18n))} />
      <ReceiptDuplicateResolution dossier={dossier} busy={busy || options.externalBusy} onBusyChange={setBusy} onChanged={setDossier} onOpenOriginal={(id) => opened.push(id)} />
    </I18nextProvider>;
  }
  await act(async () => { root.render(<View />); });
  const buttons = () => Array.from(host.querySelectorAll<HTMLButtonElement>('[data-testid="receipt-duplicate-resolution"] button'));
  const decide = () => buttons().find((button) => button.textContent?.includes("Es otra compra"));
  const flush = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  return { host, requests, opened, buttons, decide, act, flush, release, cleanup: async () => {
    release();
    await act(async () => { root.unmount(); });
    host.remove();
    globalThis.fetch = oldFetch;
  } };
}

test("the decision sends both captured versions and applies only server state", async () => {
  const ui = await mount();
  try {
    assert.match(ui.host.textContent ?? "", /Confirma que estos recibos/);
    await ui.act(async () => { ui.buttons()[0].click(); });
    assert.deepEqual(ui.opened, ["draft-original"]);
    await ui.act(async () => { ui.decide()?.click(); });
    await ui.flush();
    assert.equal(ui.requests.length, 1);
    assert.match(ui.requests[0].url, /\/business\/drafts\/draft-new\/duplicate-resolution$/);
    assert.equal(ui.requests[0].options?.method, "POST");
    assert.deepEqual(JSON.parse(String(ui.requests[0].options?.body)), { version: 7, other_draft_id: "draft-original", other_version: 3, decision: "different_purchase" });
    assert.equal(ui.host.querySelector('[data-testid="receipt-duplicate-resolution"]'), null);
    assert.match(ui.host.textContent ?? "", /Cómo se pagó/);
  } finally { await ui.cleanup(); }
});

test("in flight the warning stays visible and a second click cannot write", async () => {
  const ui = await mount("hold");
  try {
    await ui.act(async () => { ui.decide()?.click(); ui.decide()?.click(); });
    assert.equal(ui.requests.length, 1);
    assert.ok(ui.buttons().every((button) => button.disabled));
    assert.equal(ui.host.querySelector('[aria-busy="true"]') !== null, true);
    assert.match(ui.host.textContent ?? "", /Parece un recibo que ya guardaste/);
    ui.release();
    await ui.flush();
    assert.equal(ui.decide(), undefined);
  } finally { await ui.cleanup(); }
});

for (const mode of ["error", "stale"] as const) {
  test(`${mode} preserves the warning and original link; retry keeps the same key`, async () => {
    const ui = await mount(mode);
    try {
      await ui.act(async () => { ui.decide()?.click(); });
      await ui.flush();
      assert.ok(ui.host.querySelector('[role="alert"]'));
      assert.match(ui.host.textContent ?? "", /Parece un recibo que ya guardaste/);
      assert.ok(ui.buttons()[0]);
      await ui.act(async () => { ui.decide()?.click(); });
      await ui.flush();
      assert.equal(ui.requests.length, 2);
      assert.deepEqual(ui.requests[0].options?.headers, ui.requests[1].options?.headers);
      assert.deepEqual(ui.requests[0].options?.body, ui.requests[1].options?.body);
    } finally { await ui.cleanup(); }
  });
}

for (const options of [{ readOnly: true }, { closed: true }, { noCandidates: true }, { externalBusy: true }]) {
  test(`no decision for ${Object.keys(options)[0]}`, async () => {
    const ui = await mount("success", options);
    try {
      assert.ok(!ui.decide() || ui.decide()?.disabled);
      if (options.readOnly) {
        await ui.act(async () => { ui.buttons()[0].click(); });
        assert.deepEqual(ui.opened, ["draft-original"]);
      }
      assert.equal(ui.requests.length, 0);
    } finally { await ui.cleanup(); }
  });
}
