import type { GrantedSpace, ReceiptSummary } from "../../lib/business-api";

export type Capture = { input: { text: string; document_type?: string }; key: string; grant: string | null | undefined };
export type Upload = { key: string; grant: string | null | undefined };
type Answer = "lost" | "refused" | "ok";

const permissions = ["read", "prepare", "approve", "manage", "download", "export", "assign_owner"];
export const ownSpace = { space_id: "own-space", name: "Negocio propio sintético", grant_id: "grant-own", role: "owner", business_role: "owner", permissions, capabilities: ["read", "prepare", "approve"], access_seen: true } satisfies GrantedSpace;
export const clientSpace = { space_id: "client-admin", name: "Ferretería sintética", grant_id: "grant-admin", role: "accountant", business_role: "admin", permissions: permissions.slice(0, -1), capabilities: ["read", "prepare"], access_seen: true } satisfies GrantedSpace;

/**
 * The Business workspace with its Bandeja header, the way the app mounts it, driven through the Agregar door.
 * `answers` script each typed-note save and `uploadAnswers` each file upload, in order; a missing answer is "ok".
 * When `spaces` are given, the person starts in the second one.
 */
export async function mountIntakeWorkspace(answers: Answer[], spaces?: GrantedSpace[], uploadAnswers: Answer[] = []) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("../../public/locales/es-419/common.json")).default;
  const { BusinessWorkspaceProvider } = await import("../../components/business-app/BusinessWorkspace");
  const { BusinessConsentTestProvider } = await import("../../components/business-app/business-consent-context");
  const { createFixtureBusinessDataSource } = await import("../../components/business-app/fixture-data");
  const BusinessHeader = (await import("../../components/business-app/foundation/BusinessHeader")).default;
  const { useBusiness } = await import("../../components/business-app/business-context");
  /** The chat composer's "Agregar un recibo" entry, without the chat around it. */
  const ComposerDoor = () => {
    const { actions } = useBusiness();
    return <button type="button" data-testid="composer-door" onClick={() => actions.composer[0].run()} />;
  };
  const { setChosenGrant } = await import("../../lib/business-grant");
  setChosenGrant(spaces ? spaces[1].grant_id : null);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const fixture = createFixtureBusinessDataSource({ chatAvailable: false });
  const captures: Capture[] = [];
  const uploads: Upload[] = [];
  const source = {
    ...fixture,
    ...(spaces ? { spaces: async () => spaces } : {}),
    uploadReceipt: async (file: File, consent: boolean, key: string, type?: "recibo" | "venta" | null, onProgress?: (sent: number, total: number) => void, grant?: string | null) => {
      uploads.push({ key, grant });
      if (!uploadAnswers.length) return fixture.uploadReceipt(file, consent, key, type, onProgress);
      if (uploadAnswers.shift() === "lost") throw new TypeError("Failed to fetch");
      // The sample upload plays out over a second of progress; a scripted answer lands at once.
      return { id: `rcpt-${key}`, channel: "web", filename: file.name, media_type: file.type, size_bytes: file.size, received_at: new Date().toISOString(), status: "saved", error_code: null, attention: null, preparable: true, enterable: true, expense_id: null, merchant: null, occurred_on: null, amount: null, currency: null, category_id: null, account_id: null } as ReceiptSummary;
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
            <ComposerDoor />
          </BusinessWorkspaceProvider>
        </BusinessConsentTestProvider>
      </I18nextProvider>,
    );
  });
  const settle = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 25)); });
  for (let i = 0; i < 40 && !host.querySelector('[data-testid="business-primary-upload"]'); i += 1) await settle();
  const unmount = () => act(async () => root.unmount());
  const dialog = () => [...document.querySelectorAll<HTMLElement>('[role="dialog"]')].find((item) => item.textContent?.startsWith("Agregar")) ?? null;
  const button = (text: string) => [...document.querySelectorAll<HTMLButtonElement>("button")].find((item) => item.textContent === text || item.getAttribute("aria-label") === text);
  const openAgregar = async () => {
    await act(async () => host.querySelector<HTMLButtonElement>('[data-testid="business-primary-upload"]')!.click());
    for (let i = 0; i < 40 && !document.querySelector('[data-testid="intake-write-open"]'); i += 1) await settle();
  };
  const closeAgregar = async () => {
    await act(async () => dialog()!.querySelector<HTMLButtonElement>('button[aria-label="Cerrar"]')!.click());
    await settle();
  };
  const composer = () => [...document.querySelectorAll<HTMLElement>('[role="dialog"]')].find((item) => item.textContent?.startsWith("Subir recibo")) ?? null;
  const openComposer = async () => {
    await act(async () => host.querySelector<HTMLButtonElement>('[data-testid="composer-door"]')!.click());
    for (let i = 0; i < 40 && !composer()?.querySelector('input[type="file"]'); i += 1) await settle();
  };
  const closeComposer = async () => {
    await act(async () => composer()!.querySelector<HTMLButtonElement>('button[aria-label="Cerrar"]')!.click());
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
  const uploadRows = () => [...document.querySelectorAll<HTMLElement>('[data-testid="receipt-upload-row"]')].map((row) => row.dataset.status);
  const retry = () => act(async () => [...document.querySelectorAll<HTMLButtonElement>('[data-testid="receipt-typed-row"] button')].find((item) => item.textContent === "Reintentar")!.click());
  const retryFile = async (name: string) => {
    await act(async () => button(`Reintentar ${name}`)!.click());
    for (let i = 0; i < 40 && uploadRows().some((status) => status === "queued" || status === "uploading"); i += 1) await settle();
  };
  const reviewSaved = () => act(async () => button("Revisar los recibos guardados")!.click());
  const choose = (grant: string) => act(async () => { setChosenGrant(grant); await new Promise((resolve) => setTimeout(resolve, 50)); });
  /** Picks a file, and waits for its one upload attempt to answer. */
  const pickFile = async (name: string, lastModified = Date.now()) => {
    const input = document.querySelector<HTMLInputElement>('input[type="file"]:not([capture])')!;
    const transfer = new DataTransfer();
    transfer.items.add(new File(["recibo"], name, { type: "image/png", lastModified }));
    const before = uploads.length;
    await act(async () => { input.files = transfer.files; input.dispatchEvent(new Event("change", { bubbles: true })); });
    for (let i = 0; i < 40 && (uploads.length === before || uploadRows().some((status) => status === "queued" || status === "uploading")); i += 1) await settle();
  };
  return { captures, uploads, dialog, button, openAgregar, closeAgregar, composer, openComposer, closeComposer, writeNote, rows, uploadRows, retry, retryFile, reviewSaved, settle, choose, pickFile, unmount };
}
