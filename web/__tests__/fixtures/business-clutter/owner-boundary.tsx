import assert from "node:assert/strict";
import { afterAll, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { GrantedSpace } from "@/lib/business-api";
let owner = "owner-a";
const listeners = new Set<(event: string, session: { user: { id: string } }) => void>();
mock.module("@/lib/supabase-client", () => ({ getSupabaseClient: () => ({ auth: {
  getSession: async () => ({ data: { session: { user: { id: owner } } }, error: null }),
  onAuthStateChange: (listener: (event: string, session: { user: { id: string } }) => void) => { listeners.add(listener); return { data: { subscription: { unsubscribe: () => listeners.delete(listener) } } }; },
} }) }));
mock.module("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(), useRouter: () => ({ push() {}, replace() {} }), usePathname: () => "/biz" }));
mock.module("@/components/chat/ConversationShellGuard", () => ({ default: () => null }));
mock.module("@/components/business-app/ConversationUnavailableNotice", () => ({ default: () => null }));
let Probe: () => React.ReactNode = () => null;
mock.module("@/components/chat/ChatInterface", () => ({ default: () => <Probe /> }));
beforeAll(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "false"; GlobalRegistrator.register({ url: "http://localhost/biz" }); Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true }); });
afterAll(async () => { await GlobalRegistrator.unregister(); });

test("actual BusinessApp owner boundary rejects delayed prior-owner dismissal and listing", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessContextCue } = await import("@/components/business-app/BusinessPanel");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { liveBusinessDataSource } = await import("@/components/business-app/business-data");
  const { setChosenGrant } = await import("@/lib/business-grant");
  const { default: BusinessApp } = await import("@/components/business-app/BusinessApp");
  const original = { ...liveBusinessDataSource };
  const seen = new Set<string>();
  let releaseDismissal!: () => void;
  let releaseListing!: () => void;
  let holdListing = false;
  const spaces = (actor: string): GrantedSpace[] => [{ space_id: "same-business", name: actor, grant_id: `${actor}-grant`, role: "accountant", capabilities: ["read", "prepare"], access_seen: seen.has(actor) }];
  Object.assign(liveBusinessDataSource, createFixtureBusinessDataSource(), {
    spaces: async () => { const result = spaces(owner); if (holdListing) { holdListing = false; await new Promise<void>((done) => { releaseListing = done; }); } return result; },
    markAccessSeen: async () => { const actor = owner; await new Promise<void>((done) => { releaseDismissal = done; }); seen.add(actor); },
  });
  let api!: BusinessContextValue;
  Probe = function AccessProbe() { api = useBusiness(); return <BusinessContextCue />; };
  const i18n = i18next.createInstance(); await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div"); document.body.appendChild(host); const root = createRoot(host);
  const settle = () => act(async () => { await new Promise((done) => setTimeout(done, 250)); });
  const banner = () => host.querySelector('[data-testid="business-access-line"]');
  try {
    setChosenGrant("owner-a-grant");
    await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessApp /></I18nextProvider>)); await settle();
    assert.ok(banner());
    await act(async () => { (banner()!.querySelector("button") as HTMLButtonElement).click(); });
    holdListing = true; await act(async () => api.reload());
    await act(async () => { owner = "owner-b"; setChosenGrant("owner-b-grant"); for (const listener of listeners) listener("SIGNED_IN", { user: { id: owner } }); });
    await settle();
    assert.equal(api.chosen?.grant_id, "owner-b-grant", "the real app must remount its provider for the new authenticated owner");
    assert.ok(banner());
    await act(async () => { releaseDismissal(); releaseListing(); }); await settle();
    assert.equal(api.chosen?.grant_id, "owner-b-grant"); assert.ok(banner()); assert.equal(seen.has("owner-b"), false);
  } finally { await act(async () => root.unmount()); host.remove(); Object.assign(liveBusinessDataSource, original); setChosenGrant(null); }
});
