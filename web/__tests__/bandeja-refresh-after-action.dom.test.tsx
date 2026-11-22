import assert from "node:assert/strict";
import { afterAll, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReceiptActivityCounts, ReceiptDetail, ReceiptPage, ReceiptSummary } from "@/lib/business-api";
import type { BusinessDossier } from "@/lib/business-dossier";

// The real workspace on a live Business over a small in-memory server: three receipts wait for review. The
// background change check is answered by hand, so the test decides when an older answer lands.
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

let registeredFetch: typeof globalThis.fetch;
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 800, height: 900 });
  registeredFetch = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error("Unavailable"); };
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  globalThis.fetch = registeredFetch;
  await GlobalRegistrator.unregister();
});

test("a Bandeja refresh that started before an approval never overwrites the counts the approval's reload showed (#2116)", async () => {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
  const BusinessPanel = (await import("@/components/business-app/BusinessPanel")).default;
  const BusinessInboxPanel = (await import("@/components/business-app/BusinessInboxPanel")).default;
  const BusinessSidebarNav = (await import("@/components/business-app/BusinessSidebarNav")).default;
  const BusinessBottomTabs = (await import("@/components/business-app/BusinessBottomTabs")).default;
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });

  const fixture = createFixtureBusinessDataSource({ chatAvailable: true });
  const template = await fixture.receipt("rcpt-ferreteria");
  const ready = await fixture.dossier(dossierFixtureIds.ready);
  const capabilities: ("read" | "prepare" | "approve")[] = ["read", "prepare", "approve"];
  let receipts: ReceiptDetail[] = ["Uno", "Dos", "Tres"].map((merchant) => ({
    ...template, id: `rcpt-${merchant}`, merchant, draft_id: `draft-${merchant}`, version: 2, missing_fields: [],
    record_context: { ...template.record_context!, capabilities },
  }));
  const dossiers = new Map<string, BusinessDossier>(receipts.map((item) => [item.draft_id!, {
    ...structuredClone(ready), draft_id: item.draft_id!, capabilities: capabilities as BusinessDossier["capabilities"],
    facts: { ...ready.facts, counterparty: { ...ready.facts.counterparty, state: "known", value: item.merchant! } } as BusinessDossier["facts"],
  }]));
  const pending = () => receipts.filter((item) => item.status !== "confirmed");
  const answer = (waiting: number): ReceiptPage => {
    const activity: ReceiptActivityCounts = { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: waiting, ready_to_review_count: waiting, bandeja_attention_count: waiting, bandeja_listo_count: 0, confirmed_count: 3 - waiting, dismissed_count: 0 };
    return { items: pending() as ReceiptSummary[], activity, version: `"v${3 - waiting}"` };
  };
  const checks: ((page: ReceiptPage | null) => void)[] = [];
  const source = {
    ...fixture,
    mode: "live" as const,
    spaces: async () => [{ space_id: "s-own", name: "Ferretería Luna", grant_id: "g-own", role: "owner", business_role: "owner", permissions: ["read", "prepare", "approve", "manage"], capabilities }],
    emailDeliveries: async () => [],
    receipts: async () => pending() as ReceiptSummary[],
    receiptPage: async () => answer(pending().length),
    receiptChanges: () => new Promise<ReceiptPage | null>((resolve) => { checks.push(resolve); }),
    receipt: async (id: string) => structuredClone(receipts.find((item) => item.id === id)!),
    dossier: async (id: string) => structuredClone(dossiers.get(id)!),
    approveDraft: async (id: string) => {
      const current = dossiers.get(id)!;
      const recorded: BusinessDossier = { ...current, version: current.version + 1, review_state: "accepted", approval_result: { status: "recorded", activity_id: `expense-${id}`, reviewed_version: current.version, approved_revision: current.version, approved_at: "2026-10-10T14:40:00Z", actor: { actor_id: "a", actor_kind: "member", display_name: "Lucía", grant_id: "g-own", issuer_id: "a", issuer_display_name: "Lucía" } } };
      dossiers.set(id, recorded);
      receipts = receipts.map((item) => (item.draft_id === id ? { ...item, status: "confirmed", version: item.version + 1 } : item));
      return { ...structuredClone(recorded), inbox_counts: answer(pending().length).activity };
    },
  };

  let api: ReturnType<typeof useBusiness> | null = null;
  const shell = { currentView: "workspace" as const, conversationId: null, isBelowTablet: false, sidebarCollapsed: false, greetingName: null, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined };
  function Probe() {
    api = useBusiness();
    return <div>
      <div data-testid="sidebar"><BusinessSidebarNav shell={shell} /></div>
      <BusinessBottomTabs shell={shell} />
      <div data-testid="bandeja"><BusinessInboxPanel /></div>
      <div data-testid="panel"><BusinessPanel /></div>
    </div>;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const settle = async (done: () => boolean) => {
    for (let i = 0; i < 80 && !done(); i += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
  };
  const sidebarBadge = () => host.querySelector('[data-testid="business-inbox-count"]')?.textContent ?? null;
  const tabBadge = () => host.querySelector('[data-testid="business-bottom-tabs"] button span.absolute')?.textContent ?? null;
  const attentionTab = () => host.querySelector('[data-testid="bandeja"] [data-testid="reception-count-attention"]')?.textContent ?? null;
  const shown = () => [sidebarBadge(), tabBadge(), attentionTab()];
  const approve = () => [...host.querySelectorAll<HTMLButtonElement>('[data-testid="panel"] button')].find((item) => item.textContent === "Aceptar") ?? null;
  try {
    await act(async () => root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source as never}><Probe /></BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    ));
    await settle(() => sidebarBadge() === "3" && attentionTab() === "3");
    await act(async () => api!.openPanel({ kind: "receipt", receiptId: "rcpt-Uno", list: "inbox", reviewList: { scope: "inbox", receiptIds: ["rcpt-Uno", "rcpt-Dos", "rcpt-Tres"] } }));
    await settle(() => approve() !== null);
    assert.deepEqual(shown(), ["3", "3", "3"], "before the approval: badge, phone tab and Bandeja tab all show 3");

    // The person comes back to the tab: a background check starts and the server will answer from before the approval.
    await act(async () => window.dispatchEvent(new Event("focus")));
    await settle(() => checks.length === 1);
    assert.equal(checks.length, 1, "a background check is in flight");
    const older = answer(3);

    const button = approve();
    assert.ok(button, "Aceptar is on the page");
    await act(async () => button.click());
    const confirmation = [...document.querySelectorAll<HTMLButtonElement>('[role="alertdialog"] button')].find((item) => item.textContent === "Aceptar");
    if (confirmation) await act(async () => confirmation.click());
    await settle(() => sidebarBadge() === "2" && tabBadge() === "2" && attentionTab() === "2");
    assert.deepEqual(shown(), ["2", "2", "2"], "the approval's reload shows 2");

    checks[0](older);
    await settle(() => false);
    assert.deepEqual(shown(), ["2", "2", "2"], "the older check's 3 never replaces the newer 2");
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});
