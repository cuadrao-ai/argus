import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { ChatShellBridge } from "@/components/chat/ChatWorkspace";

// A link to a record (`/biz?receipt=<id>`, `/biz?expense=<id>`, `/biz?draft=<id>`, `/biz?email=<id>`) restores its panel from the address. A record
// the server no longer has (404) closes that panel, returns to its list with the address cleared and says so
// once; any other failure keeps the panel with the shared retry line, never a guess that it was removed.
let search = "";
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(search),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

type Source = ReturnType<typeof import("@/components/business-app/fixture-data").createFixtureBusinessDataSource>;
type Viewport = { name: string; width: number };
const DESKTOP: Viewport = { name: "desktop", width: 1440 };
const PHONE: Viewport = { name: "phone", width: 390 };

const cleanups: (() => Promise<void>)[] = [];
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: DESKTOP.width, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  const { clearToasts } = await import("@/components/business-app/foundation/toasts");
  clearToasts();
  document.body.innerHTML = "";
  window.history.replaceState(null, "", "/biz");
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

function failure(status: number, code: string) {
  return Object.assign(new Error(code), { status, code, requestId: `req-${status}` });
}

async function mount(url: string, viewport: Viewport, override: (fixture: Source) => Partial<Pick<Source, "receipt" | "expense" | "dossier" | "emailDelivery" | "emailDeliveries">>) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width: viewport.width, height: 900 });
  search = url.slice(url.indexOf("?"));
  window.history.replaceState(null, "", url);
  const { act, useEffect } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider, useBusiness } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { default: BusinessPanel } = await import("@/components/business-app/BusinessPanel");
  const { useChatWorkspace } = await import("@/components/chat/ChatWorkspace");
  const { useToasts } = await import("@/components/business-app/foundation/toasts");
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  const asked: string[] = [];
  const custom = { ...fixture, ...override(fixture) };
  const source: Source = {
    ...custom,
    receipt: (id, signal) => { asked.push(id); return custom.receipt(id, signal); },
    expense: (id) => { asked.push(id); return custom.expense(id); },
    dossier: (id) => { asked.push(id); return custom.dossier(id); },
    emailDelivery: (id) => { asked.push(id); return custom.emailDelivery(id); },
  };
  const isBelowTablet = viewport.width < 720;
  const shell: ChatShellBridge = { currentView: "workspace", conversationId: null, isBelowTablet, sidebarCollapsed: false, greetingName: null, showWorkspace: () => undefined, newChat: () => undefined, prepareQuestion: () => undefined };
  const toasts = new Map<number, string>();
  let api: ReturnType<typeof useBusiness> | null = null;
  function Shell() {
    api = useBusiness();
    const workspace = useChatWorkspace();
    const onShellChange = workspace?.onShellChange;
    useEffect(() => { onShellChange?.(shell); }, [onShellChange]);
    for (const toast of useToasts()) toasts.set(toast.id, toast.text);
    return null;
  }
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source} userId="user-1">
            <Shell />
            <BusinessPanel />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  cleanups.push(async () => { await act(async () => root.unmount()); host.remove(); });
  const settle = async (done: () => boolean, label: string) => {
    for (let i = 0; i < 80 && !done(); i += 1) await act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
    assert.ok(done(), label);
  };
  const quiet = async () => { await act(async () => { await new Promise((resolve) => setTimeout(resolve, 200)); }); };
  return { host, settle, quiet, asked, toasts, api: () => api!, text: () => document.body.textContent ?? "" };
}

describe("a link to a receipt the server no longer has", () => {
  for (const viewport of [DESKTOP, PHONE]) {
    test(`${viewport.name}: returns to the Bandeja with the address cleared and one notice`, async () => {
      const page = await mount("/biz?receipt=rcpt-gone", viewport, (fixture) => ({ receipt: async (id, signal) => {
        if (id === "rcpt-gone") throw failure(404, "receipt_not_found");
        return fixture.receipt(id, signal);
      } }));
      await page.settle(() => page.api().panel.kind === "inbox", "the dead panel closed onto its list");
      await page.settle(() => Boolean(page.host.querySelector('[data-testid="reception-preview"]')), "the Bandeja shows");
      await page.quiet();
      assert.equal(page.host.querySelector('[data-testid="receipt-load-error"]'), null, "no dead panel");
      assert.equal(document.querySelector('[data-testid="side-drawer"]'), null, "no record tray");
      assert.equal(new URLSearchParams(window.location.search).get("receipt"), null, window.location.search);
      assert.deepEqual([...page.toasts.values()], ["Ese recibo ya no está"], "one notice");
      assert.equal(document.querySelectorAll('[data-testid="toast-viewport"] > *').length, 1);
      assert.deepEqual(page.asked, ["rcpt-gone"], "a gone receipt is asked for once");
      assert.ok(!page.text().includes("quitado"));
    });
  }

  test("a receipt opened from Registros returns to Registros", async () => {
    const page = await mount("/biz?view=transactions", DESKTOP, (fixture) => ({ receipt: async (id, signal) => {
      if (id === "rcpt-gone") throw failure(404, "receipt_not_found");
      return fixture.receipt(id, signal);
    } }));
    await page.settle(() => page.api().records.inbox !== null, "the workspace loaded");
    const { act } = await import("react");
    await act(async () => { page.api().openPanel({ kind: "receipt", receiptId: "rcpt-gone", list: "transactions" }); });
    await page.settle(() => page.api().panel.kind === "transactions", "back on Registros");
    assert.deepEqual([...page.toasts.values()], ["Ese recibo ya no está"]);
    assert.equal(new URLSearchParams(window.location.search).get("receipt"), null);
  });
});

describe("a receipt link that fails for any other reason", () => {
  test("keeps the panel with the shared retry line, and Reintentar loads it", async () => {
    let down = true;
    const page = await mount("/biz?receipt=rcpt-ferreteria", DESKTOP, (fixture) => ({ receipt: async (id, signal) => {
      if (down) throw failure(500, "internal_error");
      return fixture.receipt(id, signal);
    } }));
    await page.settle(() => Boolean(page.host.querySelector('[data-testid="receipt-load-error"]') ?? document.querySelector('[data-testid="receipt-load-error"]')), "the retry card shows");
    const card = document.querySelector('[data-testid="receipt-load-error"]')!;
    assert.ok(card.querySelector('[role="alert"]')?.textContent?.includes("No pudimos actualizar."), card.textContent ?? "");
    assert.ok(card.querySelector('[data-testid="error-reference"]')?.textContent?.includes("Ref."));
    assert.ok(!page.text().includes("quitado"));
    assert.equal(page.api().panel.kind, "receipt");
    assert.equal(new URLSearchParams(window.location.search).get("receipt"), "rcpt-ferreteria");
    assert.equal(page.toasts.size, 0, "no notice");
    down = false;
    const { act } = await import("react");
    const retry = [...card.querySelectorAll("button")].find((button) => button.textContent === "Reintentar")!;
    await act(async () => { retry.click(); });
    await page.settle(() => Boolean(document.querySelector('[data-testid="receipt-top-block"]')), "the receipt loads");
  });
});

describe("a link to a receipt that exists", () => {
  test("opens it", async () => {
    const page = await mount("/biz?receipt=rcpt-ferreteria", DESKTOP, () => ({}));
    await page.settle(() => Boolean(document.querySelector('[data-testid="receipt-top-block"]')), "the receipt opens");
    assert.equal(page.api().panel.kind, "receipt");
    assert.equal(new URLSearchParams(window.location.search).get("receipt"), "rcpt-ferreteria");
    assert.equal(page.toasts.size, 0);
  });
});

describe("a link to an expense the server no longer has", () => {
  for (const viewport of [DESKTOP, PHONE]) {
    test(`${viewport.name}: returns to Registros with the address cleared and one notice`, async () => {
      const page = await mount("/biz?expense=exp-gone", viewport, () => ({}));
      await page.settle(() => page.api().panel.kind === "transactions", "the dead panel closed onto Registros");
      await page.settle(() => Boolean(page.host.querySelector('[data-testid="transacciones"]')), "Registros shows");
      await page.quiet();
      assert.equal(document.querySelector('[data-testid="business-expense-detail"]'), null, "no dead panel");
      assert.equal(document.querySelector('[data-testid="side-drawer"]'), null, "no record tray");
      assert.equal(new URLSearchParams(window.location.search).get("expense"), null, window.location.search);
      assert.deepEqual([...page.toasts.values()], ["Ese gasto ya no está"], "one notice");
      assert.equal(document.querySelectorAll('[data-testid="toast-viewport"] > *').length, 1);
      assert.deepEqual(page.asked, ["exp-gone"], "a gone expense is asked for once");
      assert.ok(!page.text().includes("quitado"));
    });
  }
});

describe("an expense link that fails for any other reason", () => {
  test("keeps the panel with the shared retry line, and Reintentar loads it", async () => {
    let down = true;
    const page = await mount("/biz?expense=exp-gas", DESKTOP, (fixture) => ({ expense: async (id) => {
      if (down) throw failure(500, "internal_error");
      return fixture.expense(id);
    } }));
    await page.settle(() => Boolean(document.querySelector('[data-testid="expense-load-error"]')), "the retry card shows");
    const card = document.querySelector('[data-testid="expense-load-error"]')!;
    assert.ok(card.querySelector('[role="alert"]')?.textContent?.includes("No pudimos actualizar."), card.textContent ?? "");
    assert.ok(card.querySelector('[data-testid="error-reference"]')?.textContent?.includes("Ref."));
    assert.ok(!page.text().includes("quitado"));
    assert.equal(page.api().panel.kind, "expense");
    assert.equal(new URLSearchParams(window.location.search).get("expense"), "exp-gas");
    assert.equal(page.toasts.size, 0, "no notice");
    down = false;
    const { act } = await import("react");
    const retry = [...card.querySelectorAll("button")].find((button) => button.textContent === "Reintentar")!;
    await act(async () => { retry.click(); });
    await page.settle(() => document.querySelector("#expense-detail-title")?.textContent === "Estación Ruta 3", "the expense loads");
  });
});

describe("a link to a draft the server no longer has", () => {
  for (const viewport of [DESKTOP, PHONE]) {
    test(`${viewport.name}: returns to the Bandeja with the address cleared and one notice`, async () => {
      const page = await mount("/biz?draft=draft-gone", viewport, () => ({}));
      await page.settle(() => page.api().panel.kind === "inbox", "the dead panel closed onto its list");
      await page.settle(() => Boolean(page.host.querySelector('[data-testid="reception-preview"]')), "the Bandeja shows");
      await page.quiet();
      assert.equal(document.querySelector('[data-testid="receipt-load-error"]'), null, "no dead panel");
      assert.equal(document.querySelector('[data-testid="side-drawer"]'), null, "no record tray");
      assert.equal(new URLSearchParams(window.location.search).get("draft"), null, window.location.search);
      assert.deepEqual([...page.toasts.values()], ["Ese recibo ya no está"], "one notice");
      assert.equal(document.querySelectorAll('[data-testid="toast-viewport"] > *').length, 1);
      assert.deepEqual(page.asked, ["draft-gone"], "a gone draft is asked for once");
      assert.ok(!page.text().includes("acceso actual"));
    });
  }
});

describe("a draft link that fails for any other reason", () => {
  test("keeps the panel with the shared retry line, and Reintentar loads it", async () => {
    const { dossierFixtureIds } = await import("@/components/business-app/dossier-fixtures");
    let down = true;
    const page = await mount(`/biz?draft=${dossierFixtureIds.ready}`, DESKTOP, (fixture) => ({ dossier: async (id) => {
      if (down) throw failure(500, "internal_error");
      return fixture.dossier(id);
    } }));
    await page.settle(() => Boolean(document.querySelector('[data-testid="receipt-load-error"]')), "the retry card shows");
    const card = document.querySelector('[data-testid="receipt-load-error"]')!;
    assert.ok(card.querySelector('[role="alert"]')?.textContent?.includes("No pudimos actualizar."), card.textContent ?? "");
    assert.ok(card.querySelector('[data-testid="error-reference"]')?.textContent?.includes("Ref."));
    assert.ok(!page.text().includes("acceso actual"));
    assert.equal(page.api().panel.kind, "draft");
    assert.equal(new URLSearchParams(window.location.search).get("draft"), dossierFixtureIds.ready);
    assert.equal(page.toasts.size, 0, "no notice");
    down = false;
    const { act } = await import("react");
    const retry = [...card.querySelectorAll("button")].find((button) => button.textContent === "Reintentar")!;
    await act(async () => { retry.click(); });
    await page.settle(() => Boolean(document.querySelector('[data-testid="business-record-review"]')) && !document.querySelector('[data-testid="receipt-load-error"]'), "the draft loads");
  });

  test("a refusal of access still says so", async () => {
    const page = await mount("/biz?draft=draft-refused", DESKTOP, () => ({ dossier: async () => { throw failure(403, "permission_denied"); } }));
    await page.settle(() => Boolean(document.querySelector('[data-testid="receipt-load-error"]')), "the refusal shows");
    assert.ok(document.querySelector('[data-testid="receipt-load-error"]')?.textContent?.includes("Este registro no está disponible con tu acceso actual."));
    assert.equal(page.api().panel.kind, "draft");
    assert.equal(page.toasts.size, 0);
  });
});

describe("a link to an email the server no longer has", () => {
  for (const viewport of [DESKTOP, PHONE]) {
    test(`${viewport.name}: returns to the Bandeja with the address cleared and one notice`, async () => {
      const page = await mount("/biz?email=email-gone", viewport, () => ({}));
      await page.settle(() => page.api().panel.kind === "inbox", "the dead panel closed onto the Bandeja");
      await page.settle(() => Boolean(page.host.querySelector('[data-testid="reception-preview"]')), "the Bandeja shows");
      await page.quiet();
      assert.equal(document.querySelector('[data-testid="email-record"]'), null, "no stuck email panel");
      assert.equal(document.querySelector('[data-testid="side-drawer"]'), null, "no record tray");
      assert.equal(new URLSearchParams(window.location.search).get("email"), null, window.location.search);
      assert.deepEqual([...page.toasts.values()], ["No encontramos este correo."], "one notice");
      assert.equal(document.querySelectorAll('[data-testid="toast-viewport"] > *').length, 1);
      assert.deepEqual(page.asked, ["email-gone"], "a gone email is asked for once");
    });
  }
});

describe("an email link the loaded list does not carry", () => {
  test("asks the server for it and opens it", async () => {
    const page = await mount("/biz?email=email-ferreteria", DESKTOP, (fixture) => ({
      emailDeliveries: async () => (await fixture.emailDeliveries()).filter((item) => item.id !== "email-ferreteria"),
    }));
    await page.settle(() => Boolean(document.querySelector('[data-testid="email-detail"]')), "the email opens");
    assert.equal(page.api().panel.kind, "email");
    assert.equal(new URLSearchParams(window.location.search).get("email"), "email-ferreteria");
    assert.equal(page.toasts.size, 0);
  });

  test("any other failure keeps the panel with the shared retry line, and Reintentar loads it", async () => {
    let down = true;
    const page = await mount("/biz?email=email-ferreteria", DESKTOP, (fixture) => ({
      emailDeliveries: async () => (await fixture.emailDeliveries()).filter((item) => item.id !== "email-ferreteria"),
      emailDelivery: async (id) => {
        if (down) throw failure(500, "internal_error");
        return fixture.emailDelivery(id);
      },
    }));
    await page.settle(() => Boolean(document.querySelector('[data-testid="email-load-error"]')), "the retry line shows");
    const card = document.querySelector('[data-testid="email-load-error"]')!;
    assert.ok(card.querySelector('[role="alert"]')?.textContent?.includes("No pudimos actualizar."), card.textContent ?? "");
    assert.ok(card.querySelector('[data-testid="error-reference"]')?.textContent?.includes("Ref."));
    assert.ok(!page.text().includes("No encontramos este correo."));
    assert.equal(page.api().panel.kind, "email");
    assert.equal(new URLSearchParams(window.location.search).get("email"), "email-ferreteria");
    assert.equal(page.toasts.size, 0, "no notice");
    down = false;
    const { act } = await import("react");
    const retry = [...card.querySelectorAll("button")].find((button) => button.textContent === "Reintentar")!;
    await act(async () => { retry.click(); });
    await page.settle(() => Boolean(document.querySelector('[data-testid="email-detail"]')), "the email loads");
  });
});
