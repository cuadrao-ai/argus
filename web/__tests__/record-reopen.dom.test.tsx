import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessDataSource } from "@/components/business-app/business-data";

// Reabrir on an approved record: the action shows only when the server says
// it may, one confirm with the agreed words, the confirmed call goes out with
// the record's version, and the answer (the open draft) replaces the record
// on screen. A refusal says what was refused with its Ref. and changes nothing.

mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeAll(() => {
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1280, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
  if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
  else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock;
});

const cleanups: (() => Promise<void>)[] = [];
afterEach(async () => {
  while (cleanups.length) await cleanups.pop()!();
  document.body.innerHTML = "";
});

type Dossier = Awaited<ReturnType<BusinessDataSource["dossier"]>>;
type Options = {
  /** What the server would answer on this dossier before it is shown. */
  serve?: (dossier: Dossier) => void;
  /** What the server answers to the reopen itself; the fixture's own answer by default. */
  reopen?: (id: string, version: number, key: string) => Promise<Dossier>;
};

async function mount({ serve = () => undefined, reopen }: Options = {}) {
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
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });

  const fixture = createFixtureBusinessDataSource({ chatAvailable: true });
  const draftId = dossierFixtureIds.fiscal;
  const start = await fixture.dossier(draftId);
  if (start.approval_available) await fixture.approveDraft(draftId, start.version, "approve-first", start.approval_action!);

  const sent: { version: number; key: string }[] = [];
  const served = async (read: Promise<Dossier>) => { const dossier = await read; serve(dossier); return dossier; };
  const source = {
    ...fixture,
    mode: "live" as const,
    dossier: (id: string) => served(fixture.dossier(id)),
    reopenDraft: async (id: string, version: number, key: string) => {
      sent.push({ version, key });
      return (reopen ?? fixture.reopenDraft)(id, version, key);
    },
  };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    if (new URL(String(input), "http://127.0.0.1").pathname.endsWith("/me")) return Response.json({ user: { id: "synthetic-person", email: "persona@example.com" } });
    return Response.json({ items: [], controls: {} });
  }) as typeof fetch;

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
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source as never}>
            <Probe />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  cleanups.push(async () => { await act(async () => root.unmount()); globalThis.fetch = originalFetch; });
  const wait = async (done: () => boolean, what: string) => {
    for (let i = 0; i < 80; i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
      if (done()) return;
    }
    throw new Error(`timed out waiting for ${what}: ${document.body.textContent?.slice(0, 400)}`);
  };
  const facts = () => document.querySelector<HTMLElement>('[data-testid="receipt-current-facts"]');
  const button = () => document.querySelector<HTMLButtonElement>('[data-testid="reopen-record"]');
  const dialog = () => document.querySelector<HTMLElement>('[role="alertdialog"], [role="dialog"]');
  const click = async (element: HTMLElement | null, what: string) => {
    assert.ok(element, what);
    await act(async () => element!.click());
  };
  await act(async () => api!.openPanel({ kind: "draft", draftId, list: "transactions" }));
  await wait(() => facts() !== null, "the record's dossier");
  return { act, wait, sent, facts, button, dialog, click, draftId, start };
}

describe("Reabrir on an approved record", () => {
  test("asks once with the agreed words, sends the version, and the record becomes an open draft", async () => {
    const page = await mount();
    assert.match(document.body.textContent ?? "", /Se registró un gasto/);
    const reopen = page.button();
    assert.ok(reopen, "the approved record offers Reabrir");
    assert.equal(reopen!.textContent, "Reabrir");

    await page.click(reopen, "Reabrir opens the confirm");
    await page.wait(() => page.dialog() !== null, "the confirm");
    const text = page.dialog()!.textContent ?? "";
    assert.match(text, /¿Reabrir este recibo\?/);
    assert.match(text, /Vuelve a la Bandeja para corregirlo\. Sale de tus registros hasta que lo apruebes de nuevo\./);
    assert.deepEqual(page.sent, [], "nothing goes out before the confirm");

    const confirm = [...page.dialog()!.querySelectorAll("button")].find((item) => item.textContent?.trim() === "Reabrir");
    await page.click(confirm ?? null, "the confirm button");
    await page.wait(() => page.sent.length === 1 && page.dialog() === null, "the reopen to go out and the confirm to close");
    assert.equal(page.sent[0].version, page.start.version + 1, "the approved record's version goes with it");
    await page.wait(() => page.button() === null, "Reabrir to leave the open draft");
    assert.doesNotMatch(document.body.textContent ?? "", /Se registró un gasto/, "the recorded line is gone");
    assert.ok(document.body.textContent?.includes("Aprobar"), "the open draft can be approved again");
  });

  test("a record the server will not reopen offers nothing", async () => {
    const page = await mount({ serve: (dossier) => { dossier.reopen_available = false; } });
    assert.match(document.body.textContent ?? "", /Se registró un gasto/);
    assert.equal(page.button(), null, "no Reabrir when the server says no");
  });

  test("a refusal says what was refused with its Ref. and the record stays", async () => {
    const page = await mount({
      reopen: async () => {
        throw Object.assign(new Error("refused"), { status: 422, code: "business_record_matched", reference: "ref-12345678" });
      },
    });
    await page.click(page.button(), "Reabrir opens the confirm");
    await page.wait(() => page.dialog() !== null, "the confirm");
    const confirm = [...page.dialog()!.querySelectorAll("button")].find((item) => item.textContent?.trim() === "Reabrir");
    await page.click(confirm ?? null, "the confirm button");
    await page.wait(() => document.querySelector('[role="alert"]') !== null, "the refusal");
    const alert = document.querySelector('[role="alert"]')!.textContent ?? "";
    assert.match(alert, /conciliado con un movimiento del banco/);
    assert.match(document.body.textContent ?? "", /Ref\./);
    assert.match(document.body.textContent ?? "", /Se registró un gasto/, "the record is still recorded");
    assert.ok(page.button(), "Reabrir stays available for after the unmatch");
  });
});
