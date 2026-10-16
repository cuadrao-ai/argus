import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ReceiptDetail, ReceiptSummary } from "@/lib/business-api";
import type { BusinessDossier } from "@/lib/business-dossier";

// The real workspace provider over a small in-memory server: three receipts
// awaiting review in the Bandeja's order (Uno, Dos, Tres) with an email's own
// document between Uno and Dos, each receipt carrying a prepared record ready
// for approval. The sidebar badge and the review page render side by side.
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

type Role = "owner" | "accountant";
type Refusal = { status: number; code: string };
type Options = {
  role?: Role;
  refuse?: Refusal | null;
  /** A 200 whose approval did not record. */
  unrecorded?: "failed" | "outcome_unknown";
  /** Holds the approval or the Bandeja read that follows it until release(). */
  hold?: "approval" | "bandeja" | "next-receipt";
  nextUnavailable?: "receipt" | "dossier";
  bandejaFails?: boolean;
};

async function mount({ role = "owner", refuse = null, unrecorded, hold, bandejaFails = false, nextUnavailable }: Options = {}) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
  const BusinessPanel = (await import("@/components/business-app/BusinessPanel")).default;
  const BusinessSidebarNav = (await import("@/components/business-app/BusinessSidebarNav")).default;
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });

  const fixture = createFixtureBusinessDataSource({ chatAvailable: true });
  const template = await fixture.receipt("rcpt-ferreteria");
  const ready = await fixture.dossier(dossierFixtureIds.ready);
  const capabilities = role === "owner" ? ["read", "prepare", "approve"] : ["read", "prepare"];
  const names = { "rcpt-uno": "Uno", "rcpt-email": null, "rcpt-dos": "Dos", "rcpt-tres": "Tres" } as const;
  let receipts: ReceiptDetail[] = Object.entries(names).map(([id, merchant]) => ({
    ...template,
    id,
    merchant,
    email_original: merchant === null,
    draft_id: merchant === null ? null : `draft-${id}`,
    version: 2,
    missing_fields: [],
    record_context: { ...template.record_context!, capabilities },
  }));
  const dossiers = new Map<string, BusinessDossier>(
    receipts.filter((item) => item.draft_id).map((item) => [
      item.draft_id!,
      { ...structuredClone(ready), draft_id: item.draft_id!, capabilities: capabilities as BusinessDossier["capabilities"], facts: { ...ready.facts, counterparty: { ...ready.facts.counterparty, state: "known", value: item.merchant! } } as BusinessDossier["facts"] },
    ]),
  );
  const pending = () => receipts.filter((item) => item.status !== "confirmed");
  const approvals: [string, number, string][] = [];
  let pageReads = 0;
  let bandejaReads = 0;
  let release = () => undefined as void;
  const held = new Promise<void>((resolve) => { release = resolve; });
  const source = {
    ...fixture,
    receipts: async () => {
      bandejaReads += 1;
      if (hold === "bandeja") await held;
      if (bandejaFails) throw Object.assign(new Error("unavailable"), { status: 503 });
      return pending() as ReceiptSummary[];
    },
    receiptPage: async () => {
      pageReads += 1;
      const rows = pending();
      return { items: rows as ReceiptSummary[], activity: { reading_count: 0, unread_count: 0, presentation: "none" as const, pending_review_count: rows.filter((item) => !item.email_original).length, needs_attention_count: 0 } };
    },
    receipt: async (id: string) => {
      if (id === "rcpt-dos") {
        if (hold === "next-receipt") await held;
        if (nextUnavailable === "receipt") throw Object.assign(new Error("unavailable"), { status: 503 });
      }
      return structuredClone(receipts.find((item) => item.id === id)!);
    },
    dossier: async (id: string) => {
      if (id === "draft-rcpt-dos" && nextUnavailable === "dossier") throw Object.assign(new Error("unavailable"), { status: 503 });
      return structuredClone(dossiers.get(id)!);
    },
    approveDraft: async (id: string, version: number, key: string) => {
      approvals.push([id, version, key]);
      if (hold === "approval") await held;
      if (refuse) throw Object.assign(new Error(refuse.code), refuse);
      const current = dossiers.get(id)!;
      if (unrecorded) return { ...structuredClone(current), approval_result: { status: unrecorded, code: "ledger_unavailable", reviewed_version: current.version } } as BusinessDossier;
      const recorded: BusinessDossier = { ...current, version: current.version + 1, review_state: "accepted", approval_result: { status: "recorded", activity_id: `expense-${id}`, reviewed_version: current.version, approved_revision: current.version, approved_at: "2026-10-10T14:40:00Z", actor: { actor_id: "a", actor_kind: "owner", display_name: "Lucía", grant_id: "g", issuer_id: "a", issuer_display_name: "Lucía" } } as BusinessDossier["approval_result"] };
      dossiers.set(id, recorded);
      receipts = receipts.map((item) => (item.draft_id === id ? { ...item, status: "confirmed", version: item.version + 1 } : item));
      return structuredClone(recorded);
    },
  };

  let api: ReturnType<typeof useBusiness> | null = null;
  const shell = { currentView: "workspace" as const, conversationId: null, isBelowTablet: false, sidebarCollapsed: false, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined };
  function Probe() {
    api = useBusiness();
    return (
      <div>
        <div data-testid="sidebar"><BusinessSidebarNav shell={shell} /></div>
        <div data-testid="panel"><BusinessPanel /></div>
      </div>
    );
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
  const settle = async (done: () => boolean) => {
    for (let i = 0; i < 80; i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
      if (done()) return;
    }
  };
  const button = (name: string) => [...host.querySelectorAll<HTMLButtonElement>('[data-testid="panel"] button')].find((item) => item.textContent === name) ?? null;
  const badge = () => host.querySelector('[data-testid="business-inbox-count"]')?.textContent ?? null;
  const heading = () => host.querySelector('[data-testid="panel"] h2')?.textContent ?? null;
  await settle(() => badge() !== null);
  const open = async (receiptId: string) => {
    await act(async () => api!.openPanel({ kind: "receipt", receiptId }));
    await settle(() => heading() === names[receiptId as keyof typeof names] && (button("Aprobar gasto") !== null || (host.textContent ?? "").includes("Tu permiso")));
  };
  const click = async (name: string, done: () => boolean) => {
    const target = button(name);
    assert.ok(target, `${name} is on the page`);
    await act(async () => target.click());
    await settle(done);
  };
  return {
    act, root, host, settle, open, click, button, badge, heading, approvals,
    pageReads: () => pageReads,
    bandejaReads: () => bandejaReads,
    panel: () => api!.panel,
    workspace: () => api!,
    release: async () => {
      await act(async () => release());
      await settle(() => false);
    },
  };
}

describe("Aprobar y siguiente on the receipt review page", () => {
  test("the owner sees Aprobar y siguiente as the primary action, with Aprobar gasto beside it", async () => {
    const page = await mount();
    await page.open("rcpt-uno");
    const next = page.button("Aprobar y siguiente");
    const plain = page.button("Aprobar gasto");
    assert.ok(next, "Aprobar y siguiente is shown");
    assert.ok(plain, "Aprobar gasto stays");
    assert.ok(next.className.includes("bg-black"), "Aprobar y siguiente is the primary button");
    assert.ok(!plain.className.includes("bg-black"), "Aprobar gasto is secondary");
    await page.act(async () => page.root.unmount());
  });

  test("approving opens the next receipt in Bandeja order, skipping the email's own document, and the count comes from the server", async () => {
    const page = await mount();
    assert.equal(page.badge(), "3");
    await page.open("rcpt-uno");
    const readsBefore = page.pageReads();
    await page.click("Aprobar y siguiente", () => page.panel().kind === "receipt" && (page.panel() as { receiptId: string }).receiptId === "rcpt-dos" && page.badge() === "2");
    assert.deepEqual(page.panel(), { kind: "receipt", receiptId: "rcpt-dos" });
    assert.equal(page.badge(), "2", "the badge reads the server's pending_review_count after the approval");
    assert.ok(page.pageReads() > readsBefore, "the Bandeja page was read again from the server");
    await page.settle(() => page.button("Aprobar y siguiente") !== null);
    assert.ok(page.button("Aprobar y siguiente"), "the next receipt opens on its own review page");
    await page.act(async () => page.root.unmount());
  });

  test("the approve request is the one Aprobar gasto sends: same record, same version, one key", async () => {
    const viaNext = await mount();
    await viaNext.open("rcpt-uno");
    await viaNext.click("Aprobar y siguiente", () => viaNext.approvals.length === 1);
    await viaNext.act(async () => viaNext.root.unmount());

    const viaPlain = await mount();
    await viaPlain.open("rcpt-uno");
    await viaPlain.click("Aprobar gasto", () => viaPlain.approvals.length === 1);
    await viaPlain.settle(() => false);
    assert.deepEqual(viaPlain.panel(), { kind: "receipt", receiptId: "rcpt-uno" }, "Aprobar gasto stays on the record");
    await viaPlain.act(async () => viaPlain.root.unmount());

    assert.equal(viaNext.approvals.length, 1);
    const [[nextDraft, nextVersion, nextKey]] = viaNext.approvals;
    const [[plainDraft, plainVersion, plainKey]] = viaPlain.approvals;
    assert.deepEqual([nextDraft, nextVersion], ["draft-rcpt-uno", 2]);
    assert.deepEqual([plainDraft, plainVersion], ["draft-rcpt-uno", 2]);
    assert.equal(typeof nextKey, "string");
    assert.equal(typeof plainKey, "string");
  });

  test("the next receipt is the row after the approved one, not the top of the Bandeja", async () => {
    const page = await mount();
    await page.open("rcpt-dos");
    await page.click("Aprobar y siguiente", () => (page.panel() as { receiptId?: string }).receiptId === "rcpt-tres");
    assert.deepEqual(page.panel(), { kind: "receipt", receiptId: "rcpt-tres" });
    await page.act(async () => page.root.unmount());
  });

  test("approving the last row returns to the Bandeja, which lists the rows skipped before it", async () => {
    const page = await mount();
    await page.open("rcpt-tres");
    await page.click("Aprobar y siguiente", () => page.panel().kind === "inbox" && page.host.querySelector('[data-testid="business-inbox-receipts"]') !== null);
    await page.settle(() => false);
    assert.deepEqual(page.panel(), { kind: "inbox" }, "no jump back to an earlier row");
    const rows = page.host.querySelector('[data-testid="business-inbox-receipts"]')?.textContent ?? "";
    assert.ok(rows.includes("Uno") && rows.includes("Dos") && !rows.includes("Tres"), rows);
    await page.act(async () => page.root.unmount());
  });

  test("after advancing, keyboard focus is on the next receipt's heading", async () => {
    const page = await mount();
    await page.open("rcpt-uno");
    await page.click("Aprobar y siguiente", () => page.heading() === "Dos" && document.activeElement?.id === "receipt-review-title");
    assert.equal(document.activeElement?.id, "receipt-review-title");
    assert.equal(document.activeElement?.textContent, "Dos");
    await page.act(async () => page.root.unmount());
  });

  for (const nextUnavailable of ["receipt", "dossier"] as const) {
    test(`an unavailable next ${nextUnavailable} never hands focus to a later receipt`, async () => {
      const page = await mount({ nextUnavailable });
      await page.open("rcpt-uno");
      await page.click("Aprobar y siguiente", () => page.host.querySelector('[data-testid="panel"] [role="alert"]') !== null);
      assert.ok(page.host.querySelector('[data-testid="panel"] [role="alert"]'), "the next page failed to load");
      await page.open("rcpt-tres");
      assert.equal(page.heading(), "Tres");
      assert.notEqual(document.activeElement?.id, "receipt-review-title", "manual navigation must not consume another receipt's focus handoff");
      await page.act(async () => page.root.unmount());
    });
  }

  test("leaving the next receipt while it loads never hands focus to a later page", async () => {
    const page = await mount({ hold: "next-receipt" });
    await page.open("rcpt-uno");
    await page.click("Aprobar y siguiente", () => (page.panel() as { receiptId?: string }).receiptId === "rcpt-dos");
    assert.equal(page.heading(), null, "the intended receipt is still loading");
    await page.act(async () => page.workspace().openPanel({ kind: "expenses" }));
    await page.release();
    await page.open("rcpt-tres");
    assert.equal(page.heading(), "Tres");
    assert.notEqual(document.activeElement?.id, "receipt-review-title");
    await page.act(async () => page.root.unmount());
  });

  test("approving the last receipt waiting returns to the Bandeja and its empty state", async () => {
    const page = await mount();
    await page.open("rcpt-uno");
    await page.click("Aprobar y siguiente", () => (page.panel() as { receiptId?: string }).receiptId === "rcpt-dos");
    await page.settle(() => page.button("Aprobar y siguiente") !== null);
    await page.click("Aprobar y siguiente", () => (page.panel() as { receiptId?: string }).receiptId === "rcpt-tres");
    await page.settle(() => page.button("Aprobar y siguiente") !== null);
    await page.click("Aprobar y siguiente", () => page.panel().kind === "inbox" && (page.host.textContent ?? "").includes("Todo revisado"));
    assert.deepEqual(page.panel(), { kind: "inbox" });
    assert.ok((page.host.textContent ?? "").includes("Todo revisado"), "the empty Bandeja says everything is reviewed");
    assert.equal(page.badge(), null, "the badge shows no number once the server counts nothing waiting");
    await page.act(async () => page.root.unmount());
  });

  test("a refused approval stays on the receipt with the existing error", async () => {
    const page = await mount({ refuse: { status: 409, code: "unresolved_facts" } });
    await page.open("rcpt-uno");
    await page.click("Aprobar y siguiente", () => page.host.querySelector('[data-testid="panel"] [role="alert"]') !== null);
    await page.settle(() => false);
    assert.deepEqual(page.panel(), { kind: "receipt", receiptId: "rcpt-uno" });
    assert.equal(page.host.querySelector('[data-testid="panel"] [role="alert"]')?.textContent, "Resuelve los datos pendientes antes de aprobar.");
    assert.equal(page.badge(), "3");
    await page.act(async () => page.root.unmount());
  });

  test("an approval whose outcome is unknown stays on the receipt", async () => {
    const page = await mount({ refuse: { status: 503, code: "unavailable" } });
    await page.open("rcpt-uno");
    await page.click("Aprobar y siguiente", () => page.host.querySelector('[data-testid="panel"] [role="alert"]') !== null);
    await page.settle(() => false);
    assert.deepEqual(page.panel(), { kind: "receipt", receiptId: "rcpt-uno" });
    assert.equal(page.host.querySelector('[data-testid="panel"] [role="alert"]')?.textContent, "Todavía no se conoce el resultado de la acción. Consulta el estado guardado antes de realizar otra acción.");
    await page.act(async () => page.root.unmount());
  });

  test("a 200 whose approval failed stays on the receipt and reads nothing more", async () => {
    const page = await mount({ unrecorded: "failed" });
    await page.open("rcpt-uno");
    await page.click("Aprobar y siguiente", () => page.host.querySelector('[data-testid="panel"] [role="alert"]') !== null);
    await page.settle(() => false);
    assert.deepEqual(page.panel(), { kind: "receipt", receiptId: "rcpt-uno" });
    assert.equal(page.host.querySelector('[data-testid="panel"] [role="alert"]')?.textContent, "La aprobación no terminó. Consulta el registro actual antes de realizar otra acción.");
    assert.equal(page.bandejaReads(), 0);
    await page.act(async () => page.root.unmount());
  });

  test("a 200 whose outcome is unknown stays on the receipt and reads nothing more", async () => {
    const page = await mount({ unrecorded: "outcome_unknown" });
    await page.open("rcpt-uno");
    await page.click("Aprobar y siguiente", () => (page.host.textContent ?? "").includes("Todavía no se conoce el resultado"));
    await page.settle(() => false);
    assert.deepEqual(page.panel(), { kind: "receipt", receiptId: "rcpt-uno" });
    assert.equal(page.bandejaReads(), 0);
    await page.act(async () => page.root.unmount());
  });

  test("when the Bandeja cannot be read after a recorded approval, the Bandeja opens", async () => {
    const page = await mount({ bandejaFails: true });
    await page.open("rcpt-uno");
    await page.click("Aprobar y siguiente", () => page.panel().kind === "inbox");
    assert.deepEqual(page.panel(), { kind: "inbox" });
    assert.equal(page.approvals.length, 1);
    assert.equal(page.bandejaReads(), 1);
    await page.act(async () => page.root.unmount());
  });

  test("opening Gastos while the approval is pending keeps Gastos open when it records", async () => {
    const page = await mount({ hold: "approval" });
    await page.open("rcpt-uno");
    await page.click("Aprobar y siguiente", () => page.approvals.length === 1);
    await page.act(async () => page.workspace().openPanel({ kind: "expenses" }));
    await page.release();
    assert.deepEqual(page.panel(), { kind: "expenses" });
    assert.equal(page.bandejaReads(), 0, "nothing reads the Bandeja for a page the owner left");
    await page.act(async () => page.root.unmount());
  });

  test("switching Business while the approval is pending opens no receipt when it records", async () => {
    const page = await mount({ hold: "approval" });
    await page.open("rcpt-uno");
    await page.click("Aprobar y siguiente", () => page.approvals.length === 1);
    await page.act(async () => page.workspace().chooseBusiness("fixture-grant-client"));
    await page.release();
    assert.deepEqual(page.panel(), { kind: "overview" });
    assert.equal(page.bandejaReads(), 0);
    await page.act(async () => page.root.unmount());
  });

  test("switching Business while the Bandeja read is pending opens no receipt from the old Business", async () => {
    const page = await mount({ hold: "bandeja" });
    await page.open("rcpt-uno");
    await page.click("Aprobar y siguiente", () => page.bandejaReads() === 1);
    await page.act(async () => page.workspace().chooseBusiness("fixture-grant-client"));
    await page.release();
    assert.deepEqual(page.panel(), { kind: "overview" });
    await page.act(async () => page.root.unmount());
  });

  test("a person without approval permission never sees Aprobar y siguiente", async () => {
    const page = await mount({ role: "accountant" });
    await page.open("rcpt-uno");
    await page.settle(() => (page.host.textContent ?? "").includes("Tu permiso"));
    assert.equal(page.button("Aprobar y siguiente"), null);
    assert.equal(page.button("Aprobar gasto"), null);
    await page.act(async () => page.root.unmount());
  });
});
