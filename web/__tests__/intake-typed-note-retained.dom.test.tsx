import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { GrantedSpace } from "@/lib/business-api";

// A typed note whose save could not be confirmed outlives Agregar: closing the panel must not drop its text or its
// idempotency key, or reopening and typing it again could save a second draft when the first one did land.
mock.module("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
  usePathname: () => "/biz",
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1280, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
let unmount = async () => {};
afterEach(async () => {
  await unmount();
  unmount = async () => {};
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  document.body.innerHTML = "";
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

type Capture = { input: { text: string; document_type?: string }; key: string; grant: string | null | undefined };

async function mount(answers: ("lost" | "refused" | "ok")[], spaces?: GrantedSpace[]) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider } = await import("@/components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("@/components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const BusinessHeader = (await import("@/components/business-app/foundation/BusinessHeader")).default;
  const { setChosenGrant } = await import("@/lib/business-grant");
  setChosenGrant(spaces ? spaces[1].grant_id : null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  const captures: Capture[] = [];
  const uploads: (string | null | undefined)[] = [];
  const source = {
    ...fixture,
    ...(spaces ? { spaces: async () => spaces } : {}),
    uploadReceipt: async (file: File, consent: boolean, key: string, type?: "recibo" | "venta" | null, onProgress?: (sent: number, total: number) => void, grant?: string | null) => {
      uploads.push(grant);
      return fixture.uploadReceipt(file, consent, key, type, onProgress);
    },
    captureNote: async (input: Capture["input"], key: string, grant?: string | null) => {
      captures.push({ input, key, grant });
      const answer = answers.shift() ?? "ok";
      if (answer === "lost") throw new TypeError("Failed to fetch");
      if (answer === "refused") throw Object.assign(new Error("refused"), { status: 422, code: "validation_failed" });
      return fixture.captureNote(input, key);
    },
  };
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <BusinessConsentTestProvider accepted>
          <BusinessWorkspaceProvider source={source as never}>
            <BusinessHeader home={false} name={null} title="Bandeja" screen="inbox" />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  const settle = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
  for (let i = 0; i < 40 && !host.querySelector('[data-testid="business-primary-upload"]'); i += 1) await settle();
  unmount = () => act(async () => root.unmount());
  const dialog = () => [...document.querySelectorAll<HTMLElement>('[role="dialog"]')].find((item) => item.textContent?.startsWith("Agregar")) ?? null;
  const openAgregar = async () => {
    await act(async () => host.querySelector<HTMLButtonElement>('[data-testid="business-primary-upload"]')!.click());
    for (let i = 0; i < 40 && !document.querySelector('[data-testid="intake-write-open"]'); i += 1) await settle();
  };
  const closeAgregar = async () => {
    await act(async () => dialog()!.querySelector<HTMLButtonElement>('button[aria-label="Cerrar"]')!.click());
    await settle();
  };
  const writeNote = async (text: string, type: "Compra" | "Venta") => {
    await act(async () => document.querySelector<HTMLButtonElement>('[data-testid="intake-write-open"]')!.click());
    const field = document.querySelector<HTMLTextAreaElement>("#intake-write-text")!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(field, text);
      field.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => [...document.querySelectorAll<HTMLButtonElement>('[data-testid="intake-write-type"] button')].find((item) => item.textContent === type)!.click());
    await act(async () => document.querySelector<HTMLButtonElement>('[data-testid="intake-write-save"]')!.click());
    await settle();
  };
  const rows = () => [...document.querySelectorAll<HTMLElement>('[data-testid="receipt-typed-row"]')].map((row) => ({ status: row.dataset.status, text: row.querySelector("p")?.textContent }));
  const retry = () => act(async () => [...document.querySelectorAll<HTMLButtonElement>('[data-testid="receipt-typed-row"] button')].find((item) => item.textContent === "Reintentar")!.click());
  const choose = (grant: string) => act(async () => { setChosenGrant(grant); await new Promise((resolve) => setTimeout(resolve, 50)); });
  const pickFile = async (name: string) => {
    const input = document.querySelector<HTMLInputElement>('input[type="file"]:not([capture])')!;
    const transfer = new DataTransfer();
    transfer.items.add(new File(["recibo"], name, { type: "image/png" }));
    await act(async () => { input.files = transfer.files; input.dispatchEvent(new Event("change", { bubbles: true })); });
    for (let i = 0; i < 40 && !uploads.length; i += 1) await settle();
  };
  return { captures, uploads, dialog, openAgregar, closeAgregar, writeNote, rows, retry, settle, choose, pickFile };
}

test("an unconfirmed typed note survives closing Agregar and retries with its original key", async () => {
  const page = await mount(["lost", "ok"]);
  await page.openAgregar();
  await page.writeNote("Vendí 3 sacos de cemento a RD$1,500", "Venta");
  assert.deepEqual(page.rows(), [{ status: "uncertain", text: "Vendí 3 sacos de cemento a RD$1,500" }]);
  await page.closeAgregar();
  assert.equal(page.dialog(), null, "Agregar is closed");

  await page.openAgregar();
  assert.deepEqual(page.rows(), [{ status: "uncertain", text: "Vendí 3 sacos de cemento a RD$1,500" }], "reopening shows the same note, still unconfirmed");
  await page.retry();
  await page.settle();
  assert.equal(page.captures.length, 2);
  assert.deepEqual(page.captures[1], page.captures[0], "the retry repeats the original request and key");
  assert.deepEqual(page.captures[0].input, { text: "Vendí 3 sacos de cemento a RD$1,500", document_type: "venta" });
  assert.deepEqual(page.rows(), [{ status: "saved", text: "Vendí 3 sacos de cemento a RD$1,500" }]);

  await page.closeAgregar();
  await page.openAgregar();
  assert.deepEqual(page.rows(), [], "a saved note is finished, so closing forgets it");
});

test("closing Agregar forgets a refused typed note, which a retry would not change", async () => {
  const page = await mount(["refused"]);
  await page.openAgregar();
  await page.writeNote("Compré gasoil por RD$500", "Compra");
  assert.deepEqual(page.rows(), [{ status: "refused", text: "Compré gasoil por RD$500" }]);
  await page.closeAgregar();
  await page.openAgregar();
  assert.deepEqual(page.rows(), []);
  assert.equal(page.captures.length, 1);
});

test("an unconfirmed typed note stays with its Business, so a retry never sends it to another one", async () => {
  const own = { space_id: "own-space", name: "Negocio propio sintético", grant_id: "grant-own", role: "owner", business_role: "owner", permissions: ["read", "prepare", "approve", "manage", "download", "export", "assign_owner"], capabilities: ["read", "prepare", "approve"], access_seen: true } satisfies GrantedSpace;
  const client = { space_id: "client-admin", name: "Ferretería sintética", grant_id: "grant-admin", role: "accountant", business_role: "admin", permissions: ["read", "prepare", "manage", "download", "export"], capabilities: ["read", "prepare"], access_seen: true } satisfies GrantedSpace;
  const page = await mount(["lost"], [own, client]);
  await page.openAgregar();
  await page.writeNote("Pagué RD$900 de flete", "Compra");
  assert.deepEqual(page.rows(), [{ status: "uncertain", text: "Pagué RD$900 de flete" }]);
  await page.closeAgregar();
  await page.choose("grant-own");
  await page.openAgregar();
  assert.deepEqual(page.rows(), [], "the other Business shows no note to retry");
  await page.closeAgregar();
  await page.choose("grant-admin");
  await page.openAgregar();
  assert.deepEqual(page.rows(), [{ status: "uncertain", text: "Pagué RD$900 de flete" }], "back in its Business, the note waits for its retry");
  assert.equal(page.captures.length, 1);
  await page.retry();
  await page.settle();
  assert.deepEqual(page.captures.map((capture) => capture.grant), ["grant-admin", "grant-admin"], "both attempts name the Business the note was typed in");
});

test("a file picked in Agregar is handed to the upload with the Business Agregar is open in", async () => {
  const own = { space_id: "own-space", name: "Negocio propio sintético", grant_id: "grant-own", role: "owner", business_role: "owner", permissions: ["read", "prepare", "approve", "manage", "download", "export", "assign_owner"], capabilities: ["read", "prepare", "approve"], access_seen: true } satisfies GrantedSpace;
  const client = { space_id: "client-admin", name: "Ferretería sintética", grant_id: "grant-admin", role: "accountant", business_role: "admin", permissions: ["read", "prepare", "manage", "download", "export"], capabilities: ["read", "prepare"], access_seen: true } satisfies GrantedSpace;
  const page = await mount([], [own, client]);
  await page.openAgregar();
  await page.pickFile("factura.png");
  assert.deepEqual(page.uploads, ["grant-admin"]);
});
