import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessSearchResult } from "@/lib/business-search-api";

beforeAll(() => { GlobalRegistrator.register({ url: "http://localhost/biz" }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterAll(async () => { await GlobalRegistrator.unregister(); });

for (const held of [false, true]) test(`email off removes sender search results and ignores an earlier ${held ? "pending" : "loaded"} answer`, async () => {
  const { act, useState } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "en", resources: { en: { translation: (await import("@/public/locales/en/common.json")).default } } });
  const { useBusinessSearch } = await import("@/components/business-app/useBusinessSearch");
  const { useWorkspaceSearch } = await import("@/components/sidebar/command-palette/WorkspaceSearchResults");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const response: BusinessSearchResult = { next_cursors: {}, expenses: [], ventas: [], accounts: [], receipts: [],
    email_deliveries: [{ id: "history", sender: "sender@cuadrao.example", subject: "Historical email", state: "captured", received_at: "2026-11-04T00:00:00Z", inbox_group: "bandeja" }],
    email_senders: [{ id: "sender", kind: "address", value: "sender@cuadrao.example", status: "authorized" }] };
  let release: (() => void) | undefined;
  let requests = 0;
  const source = { ...createFixtureBusinessDataSource(), captures: async () => ({ items: [], has_more: false }), search: async () => { requests += 1; if (held && requests === 1) await new Promise<void>(resolve => { release = resolve; }); return response; } };
  let disable = () => {};
  function Harness() {
    const [emailAvailable, setAvailable] = useState(true);
    disable = () => setAvailable(false);
    const search = useBusinessSearch({ source, accounts: [], actions: { create: [], composer: [], starterEntries: [] }, canAdd: false, scope: "business", canExport: false, openExport: () => {}, openPanel: () => {}, emailAvailable });
    const result = useWorkspaceSearch(search, "sender");
    return <output>{result.state.status === "ready" ? result.state.groups.map(group => group.id).join(" ") : result.state.status}</output>;
  }
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  const settle = async (done: () => boolean) => { for (let n = 0; n < 20 && !done(); n += 1) await act(async () => { await new Promise(resolve => setTimeout(resolve, 25)); }); assert.ok(done()); };
  try {
    await act(async () => root.render(<I18nextProvider i18n={i18n}><Harness /></I18nextProvider>));
    await settle(() => held ? release !== undefined : host.textContent?.includes("email_senders") === true);
    await act(async () => disable());
    assert.ok(!host.textContent?.includes("email_senders"));
    if (release) await act(async () => release!());
    await settle(() => host.textContent?.includes("email_deliveries") === true);
    assert.ok(!host.textContent?.includes("email_senders"));
  } finally { await act(async () => root.unmount()); host.remove(); }
});
