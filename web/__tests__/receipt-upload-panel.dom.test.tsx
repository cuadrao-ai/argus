import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import { BusinessConsentTestProvider } from "@/components/business-app/business-consent-context";
import { primaryButtonClass } from "@/components/business-app/business-ui";
import ReceiptIntakeDialog from "@/components/business-app/ReceiptIntakeDialog";
import { ReceiptUploadQueue, type DocumentType } from "@/components/business-app/receipt-upload-queue";
import type { ReceiptReading, ReceiptSummary } from "@/lib/business-api";
import spanish from "@/public/locales/es-419/common.json";

const MB = 1024 * 1024;
const limits = { max_bytes: 10 * MB, media_types: ["image/jpeg", "application/pdf"] };
const photo = (name: string, bytes = 7) => new File(["x".repeat(bytes)], name, { type: "image/jpeg" });
const savedReceipt = (id: string, extra: Partial<ReceiptSummary> = {}): ReceiptSummary => ({
  id, channel: "web", title: null, filename: null, media_type: "image/jpeg", size_bytes: 7,
  received_at: "2026-11-22T12:00:00Z", status: "saved", error_code: null,
  attention: null, preparable: true, enterable: true, expense_id: null,
  merchant: null, occurred_on: null, amount: null, currency: null, category_id: null, account_id: null, ...extra,
});
const reading = (extra: Partial<ReceiptReading> = {}): ReceiptReading => ({ scope_version: 1, enabled: true, available: true, can_change: true, disclosure: "Permiso del negocio para leer sus documentos.", disclosure_token: "a".repeat(64), route: null, consented_at: null, revoked_at: null, ...extra });

const clock = { real: Date.now, now: 0 };
const cleanups: (() => Promise<void>)[] = [];
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
  for (const name of ["ondrop", "ondragover"] as const) {
    if (!(name in HTMLElement.prototype)) Object.defineProperty(HTMLElement.prototype, name, { configurable: true, writable: true, value: null });
  }
});
afterEach(async () => { while (cleanups.length) await cleanups.pop()!(); Date.now = clock.real; document.body.innerHTML = ""; });
afterAll(async () => { await GlobalRegistrator.unregister(); });

type Attempt = { name: string; key: string; documentType: DocumentType | null; progress: (sent: number, total: number) => void; finish: (receipt: ReceiptSummary) => void; fail: (error: unknown) => void };

async function mount({ read = reading() as ReceiptReading | null, email = false, whatsapp = false, address = "recibos.7f3k@entrada.example" as string | null } = {}) {
  // The queue repaints a moving file at most every 100 ms; the tests own the clock so each report shows.
  clock.now = 1_000_000;
  Date.now = () => clock.now;
  const attempts: Attempt[] = [];
  const queue = new ReceiptUploadQueue((candidate, _consent, key, documentType, onProgress) => new Promise<ReceiptSummary>((resolve, reject) => {
    attempts.push({ name: candidate.name, key, documentType, progress: onProgress, finish: resolve, fail: reject });
  }), () => undefined);
  const changes: boolean[] = [];
  const reviews: ReceiptSummary[][] = [];
  const context = {
    source: {
      setReceiptReading: async (current: ReceiptReading, enabled: boolean) => { changes.push(enabled); return { ...current, enabled }; },
      emailIntake: async () => ({ enabled: address !== null, receiving_address: address }),
    },
    chosen: { space_id: "own", capabilities: ["read", "prepare", "approve"] },
    // The workspace answer carries the reading setting; null is a server that did not say.
    records: { workspace: { accounts: [], currencies: [], assistant_available: false, chat_available: false, receipt_limits: limits, receipt_reading: read }, workspaceGrant: null, workspaceRevision: 0, error: false },
    receivingChannels: { email: { available: email }, whatsapp: { available: whatsapp } },
    revision: 0, bridge: null, reload() {}, openPanel() {},
  } as unknown as BusinessContextValue;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.body.appendChild(document.createElement("div"));
  const root = createRoot(host);
  await act(async () => root.render(
    <I18nextProvider i18n={i18n}><BusinessConsentTestProvider accepted><BusinessContext.Provider value={context}>
      <ReceiptIntakeDialog target="inbox" queue={queue} onClose={() => undefined} onReview={(saved) => reviews.push(saved)} />
    </BusinessContext.Provider></BusinessConsentTestProvider></I18nextProvider>,
  ));
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  cleanups.push(async () => { await act(async () => root.unmount()); host.remove(); });
  const picker = () => document.querySelector<HTMLInputElement>('input[type="file"]:not([capture])')!;
  const turn = () => act(async () => { for (let i = 0; i < 6; i += 1) await Promise.resolve(); });
  return {
    queue, attempts, changes, reviews, turn,
    text: () => document.body.textContent ?? "",
    choose: (...files: File[]) => act(async () => {
      const transfer = new DataTransfer();
      for (const item of files) transfer.items.add(item);
      picker().files = transfer.files;
      picker().dispatchEvent(new Event("change", { bubbles: true }));
    }),
    /** One upload report, a quarter second after the last, so the queue shows it. */
    report: (attempt: Attempt, sent: number, total: number, afterMs = 250) => act(async () => { clock.now += afterMs; attempt.progress(sent, total); }),
    settle: (run: () => void) => act(async () => { run(); for (let i = 0; i < 6; i += 1) await Promise.resolve(); }),
    rows: () => [...document.querySelectorAll<HTMLElement>('[data-testid="receipt-upload-queue"] [data-testid="receipt-upload-row"]')],
    row: (name: string) => [...document.querySelectorAll<HTMLElement>('[data-testid="receipt-upload-row"]')].find((node) => node.textContent?.includes(name)),
    button: (label: string, within: ParentNode = document) => [...within.querySelectorAll<HTMLButtonElement>("button")].find((node) => node.textContent?.trim() === label || node.getAttribute("aria-label") === label),
    click: (node: HTMLElement | null | undefined) => { assert.ok(node, "the control is on the page"); return act(async () => node.click()); },
    kind: () => [...document.querySelectorAll<HTMLButtonElement>('[data-testid="intake-document-type"] [role="radio"]')].map((node) => ({ label: node.textContent, checked: node.getAttribute("aria-checked") === "true", disabled: node.disabled })),
    kindHelp: () => document.querySelector('[data-testid="intake-type-help"]')?.textContent,
    review: () => document.querySelector<HTMLButtonElement>('[data-testid="receipt-intake-review"]'),
  };
}

test("the empty panel is one clickable zone that says what the server takes, and has no door to a typed note", async () => {
  const page = await mount();
  assert.match(document.querySelector('[role="dialog"] h2')?.textContent ?? "", /^Agregar documentos$/);
  const zone = document.querySelector<HTMLElement>('[data-testid="intake-drop-zone"]')!;
  assert.equal(zone.getAttribute("role"), "button");
  assert.equal(zone.getAttribute("aria-label"), "Elegir archivos para subir");
  assert.match(zone.textContent ?? "", /Sube tus documentos/);
  assert.match(zone.textContent ?? "", /Haz clic para elegir/);
  assert.match(zone.textContent ?? "", /JPG, PDF · hasta 10 MB cada uno/, "formats and size are the server's limits");
  let opened = 0;
  document.querySelector<HTMLInputElement>('input[type="file"]:not([capture])')!.click = () => { opened += 1; };
  await page.click(zone);
  await act(async () => { zone.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })); });
  assert.equal(opened, 2, "a click anywhere on the zone, or Enter on it, opens the picker");
  assert.doesNotMatch(page.text(), /No tienes el papel|Escríbelo/);
  assert.equal(document.querySelector('[data-testid="receipt-intake-footer"]'), null, "no footer before the first file");
});

test("a pasted file uploads like a chosen one", async () => {
  const page = await mount();
  await act(async () => {
    const event = new Event("paste", { bubbles: true, cancelable: true });
    const transfer = new DataTransfer();
    transfer.items.add(photo("pegado.jpg"));
    Object.defineProperty(event, "clipboardData", { value: transfer });
    window.dispatchEvent(event);
  });
  assert.deepEqual(page.attempts.map((attempt) => attempt.name), ["pegado.jpg"]);
});

test("a row shows each stage the queue reports: problems first, then the one sending, then the ones in line", async () => {
  const page = await mount();
  await page.choose(photo("a.jpg"), photo("b.jpg"), photo("c.jpg"), photo("pesado.jpg", 10 * MB + 1));
  assert.deepEqual(page.rows().map((row) => row.dataset.stage), ["rejected", "starting", "waiting", "waiting"]);
  assert.match(page.row("pesado.jpg")?.textContent ?? "", /Pesa más de 10 MB\. Usa una foto o un PDF más pequeño\./);
  assert.match(page.row("b.jpg")?.textContent ?? "", /En cola/);
  assert.match(page.text(), /Subiendo 1 de 3…/);
  assert.match(page.text(), /4 archivos/);

  const bar = () => page.row("a.jpg")?.querySelector('[role="progressbar"]');
  const total = () => document.querySelector('[data-testid="receipt-upload-summary-bar"] [role="progressbar"]');
  for (const unmeasured of [bar(), total()]) {
    assert.equal(unmeasured?.hasAttribute("aria-valuenow"), false, "no number before a byte is measured");
    assert.equal(unmeasured?.getAttribute("aria-busy"), "true");
    assert.equal(unmeasured?.querySelector<HTMLElement>("i")?.style.width, "", "and no width that reads as a share");
  }
  assert.doesNotMatch(page.row("a.jpg")?.textContent ?? "", /%/);
  assert.equal(bar()?.getAttribute("aria-label"), "Subiendo a.jpg");
  await page.report(page.attempts[0], 46, 100);
  assert.equal(bar()?.getAttribute("aria-valuenow"), "46");
  assert.equal(bar()?.hasAttribute("aria-busy"), false);
  assert.equal(bar()?.querySelector<HTMLElement>("i")?.style.width, "46%");
  assert.match(page.row("a.jpg")?.textContent ?? "", /46%/);
  await page.report(page.attempts[0], 100, 100);
  assert.equal(page.row("a.jpg")?.dataset.stage, "saving");
  assert.match(page.row("a.jpg")?.textContent ?? "", /Guardando…/);

  await page.settle(() => page.attempts[0].finish(savedReceipt("a")));
  const fold = () => document.querySelector<HTMLElement>('[data-testid="receipt-upload-saved-fold"]')!;
  assert.match(fold().textContent ?? "", /1 guardado/);
  assert.equal(fold().querySelector("button")?.getAttribute("aria-expanded"), "false", "saved files fold away");
  assert.equal(page.row("a.jpg"), undefined);
  assert.equal(page.row("b.jpg")?.dataset.stage, "starting");

  await page.report(page.attempts[1], 60, 100);
  await page.settle(() => page.attempts[1].fail(new TypeError("Failed to fetch")));
  assert.equal(page.row("b.jpg")?.dataset.stage, "stopped");
  assert.equal(page.row("b.jpg")?.querySelector('[role="img"]')?.getAttribute("aria-label"), "Se detuvo en 60%", "the bar stays where the bytes really got");
  assert.equal(page.row("b.jpg")?.querySelector<HTMLElement>('[role="img"] i')?.style.width, "60%");
  assert.match(page.row("b.jpg")?.querySelector('[role="alert"]')?.textContent ?? "", /Se perdió la conexión\. Se reintenta solo al volver\./);
  assert.deepEqual(page.rows().map((row) => row.dataset.stage), ["stopped", "rejected", "starting"], "the next file goes on");

  await page.settle(() => page.attempts[2].finish(savedReceipt("c", { replayed: true })));
  await page.click(page.button("Reintentar b.jpg"));
  assert.equal(page.row("b.jpg")?.dataset.stage, "starting", "a retry starts from nothing");
  assert.equal(page.row("b.jpg")?.querySelector('[role="progressbar"]')?.hasAttribute("aria-valuenow"), false);
  assert.equal(page.attempts[3].key, page.attempts[1].key, "with the same upload key");
  await page.settle(() => page.attempts[3].finish(savedReceipt("b")));
  assert.match(fold().textContent ?? "", /3 guardados/);
  await page.click(fold().querySelector("button"));
  assert.match(page.row("c.jpg")?.textContent ?? "", /Ya estaba guardado\./);
  assert.match(page.row("a.jpg")?.textContent ?? "", /Guardado/);
  assert.match(page.text(), /3 guardados · 1 sin subir/);
});

test("the X shows only on a file that waits, stopped or was refused, and takes a waiting file out during the upload", async () => {
  const page = await mount();
  await page.choose(photo("a.jpg"), photo("b.jpg"), photo("c.jpg"), photo("pesado.jpg", 10 * MB + 1));
  const remove = (name: string) => page.button(`Quitar ${name} de esta lista`);
  assert.deepEqual(["a.jpg", "b.jpg", "c.jpg", "pesado.jpg"].map((name) => Boolean(remove(name))), [false, true, true, true]);
  await page.click(remove("b.jpg"));
  await page.click(remove("pesado.jpg"));
  assert.equal(page.row("b.jpg"), undefined);
  await page.settle(() => page.attempts[0].finish(savedReceipt("a")));
  assert.deepEqual(page.attempts.map((attempt) => attempt.name), ["a.jpg", "c.jpg"], "the removed file is never sent");
  await page.click(document.querySelector<HTMLElement>('[data-testid="receipt-upload-saved-fold"] button'));
  assert.equal(remove("a.jpg"), undefined, "a saved file has no X");
  await page.settle(() => page.attempts[1].fail(new TypeError("Failed to fetch")));
  assert.ok(remove("c.jpg"), "a stopped file can leave");
});

test("the footer says closing is safe while files go, then offers to review what was saved and keeps what failed", async () => {
  const page = await mount();
  await page.choose(photo("a.jpg"), photo("b.jpg"));
  assert.match(document.querySelector('[data-testid="receipt-intake-keep"]')?.textContent ?? "", /La subida sigue si cierras este panel\. No cierres la pestaña\./);
  assert.equal(page.review()?.disabled, true);
  await page.settle(() => page.attempts[0].finish(savedReceipt("a")));
  await page.settle(() => page.attempts[1].fail(new TypeError("Failed to fetch")));
  assert.equal(document.querySelector('[data-testid="receipt-intake-keep"]'), null);
  assert.equal(page.review()?.textContent, "Revisar 1 documento");
  assert.equal(page.review()?.disabled, false);
  await page.click(page.review());
  assert.deepEqual(page.reviews.map((saved) => saved.map((receipt) => receipt.id)), [["a"]]);
  assert.deepEqual(page.queue.snapshot().map((item) => `${item.file.name}:${item.status}`), ["b.jpg:failed"], "review clears what is settled and keeps the file still to send");
});

test("two names for the same bytes are one document to review, though each file keeps its row", async () => {
  const page = await mount();
  await page.choose(photo("a.jpg"), photo("a-copia.jpg"), photo("b.jpg"));
  await page.settle(() => page.attempts[0].finish(savedReceipt("a")));
  await page.settle(() => page.attempts[1].finish(savedReceipt("a", { replayed: true })));
  await page.settle(() => page.attempts[2].finish(savedReceipt("b")));
  const fold = document.querySelector<HTMLElement>('[data-testid="receipt-upload-saved-fold"]')!;
  assert.match(fold.textContent ?? "", /2 guardados/);
  assert.equal(document.querySelector('[data-testid="receipt-upload-summary"]')?.textContent, "2 guardados");
  assert.match(page.text(), /3 archivos/);
  await page.click(fold.querySelector("button"));
  assert.match(page.row("a-copia.jpg")?.textContent ?? "", /Ya estaba guardado\./);
  assert.equal(page.review()?.textContent, "Revisar 2 documentos");
  await page.click(page.review());
  assert.deepEqual(page.reviews.map((saved) => saved.map((receipt) => receipt.id)), [["a", "b"]]);
});

test("the time left is vague and only shrinks", async () => {
  const page = await mount();
  await page.choose(photo("a.jpg", 1000));
  const left = () => document.querySelector('[data-testid="receipt-upload-time-left"]')?.textContent ?? null;
  assert.equal(left(), null, "nothing is said before there is a rate");
  await page.report(page.attempts[0], 500, 1000, 1_000);
  assert.equal(left(), "Unos segundos");
  await page.report(page.attempts[0], 510, 1000, 30_000);
  assert.equal(left(), "Unos segundos", "a slower minute does not make the wait grow back");
  assert.equal(document.querySelector('[data-testid="receipt-upload-summary-bar"] [role="progressbar"]')?.getAttribute("aria-valuenow"), "51");
  await page.report(page.attempts[0], 1000, 1000);
  assert.equal(left(), "Terminando…");
});

test("Detectar is offered only while reading is on; without reading the batch is Compras until the person says Ventas", async () => {
  const on = await mount({ read: reading({ enabled: true }) });
  assert.deepEqual(on.kind(), [{ label: "Detectar", checked: true, disabled: false }, { label: "Compras", checked: false, disabled: false }, { label: "Ventas", checked: false, disabled: false }]);
  assert.equal(on.kindHelp(), "Se detecta al leer.");
  assert.deepEqual([...document.querySelectorAll('[data-testid="intake-options"] > *')].map((row) => row.querySelector("span > span")?.textContent), ["Compra o venta"], "with reading on the options are only Compra o venta");
  assert.equal(document.querySelector('[data-testid="intake-options"] [role="switch"]'), null, "the panel has no switch while reading is on");
  await on.choose(photo("detectado.jpg"));
  await on.click(on.button("Ventas", document.querySelector<HTMLElement>('[data-testid="intake-document-type"]')!));
  assert.equal(on.kindHelp(), "Para todo lo que subas.");
  await on.choose(photo("venta.jpg"));
  await on.settle(() => on.attempts[0].finish(savedReceipt("d")));
  assert.deepEqual(on.attempts.map((attempt) => attempt.documentType), [null, "venta"], "the choice is the same document type the upload always sent");
  await cleanups.pop()!();
  document.body.innerHTML = "";

  const off = await mount({ read: reading({ enabled: false }) });
  assert.deepEqual(off.kind(), [{ label: "Detectar", checked: false, disabled: true }, { label: "Compras", checked: true, disabled: false }, { label: "Ventas", checked: false, disabled: false }]);
  assert.equal(off.kindHelp(), "Sin lectura, eliges tú.");
  assert.match(off.text(), /Leer mis documentos automáticamente/);
  assert.match(off.text(), /Tú siempre revisas y aceptas\./);
  const compras = [...document.querySelectorAll<HTMLButtonElement>('[data-testid="intake-document-type"] [role="radio"]')][1];
  await act(async () => { compras.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true })); });
  assert.equal(off.kind().find((segment) => segment.checked)?.label, "Ventas", "the arrow keys pass over Detectar");
  await off.choose(photo("sin-leer.jpg"));
  assert.equal(off.attempts[0].documentType, "venta");
});

test("an unknown reading setting shows no switch and never claims reading is off", async () => {
  const page = await mount({ read: null });
  assert.equal(document.querySelector('[data-testid="receipt-reading-control"]'), null);
  assert.equal(page.kind()[0].disabled, false);
  assert.equal(page.kind()[0].checked, true);
});

test("the owner turns reading on in the panel, beside the server's words the first time and with one flip after that; anyone else cannot", async () => {
  const toggle = () => document.querySelector<HTMLButtonElement>('[data-testid="intake-options"] [role="switch"]');
  const consent = () => document.querySelector<HTMLElement>('[data-testid="receipt-reading-consent"]');
  const first = await mount({ read: reading({ enabled: false, consented_at: null }) });
  assert.equal(first.kind()[0].disabled, true, "Detectar goes with reading");
  assert.equal(toggle()?.getAttribute("aria-label"), "Leer mis documentos automáticamente");
  assert.equal(document.querySelector('[data-testid="receipt-reading-turn-on"]'), null, "the panel keeps the switch, not the notice button");
  await first.click(toggle());
  assert.deepEqual(first.changes, [], "the first turn-on asks first");
  assert.match(consent()?.textContent ?? "", /Permiso del negocio para leer sus documentos\./);
  const confirm = consent()!.querySelector("button")!;
  assert.equal(confirm.className, primaryButtonClass);
  assert.ok(consent()!.classList.contains("items-start"));
  assert.equal(document.querySelector('[role="alertdialog"]'), null);
  await first.click(confirm);
  await first.turn();
  assert.deepEqual(first.changes, [true]);
  assert.equal(toggle(), null, "the row leaves once reading is on");
  assert.equal(consent(), null);
  assert.equal(first.kind()[0].disabled, false);
  await cleanups.pop()!();
  document.body.innerHTML = "";

  const again = await mount({ read: reading({ enabled: false, consented_at: "2026-11-01T12:00:00Z" }) });
  await again.click(toggle());
  await again.turn();
  assert.deepEqual(again.changes, [true], "a Business that agreed before flips in place");
  assert.equal(document.body.textContent?.includes("Permiso del negocio para leer sus documentos."), false);
  assert.equal(toggle(), null);
  await cleanups.pop()!();
  document.body.innerHTML = "";

  await mount({ read: reading({ enabled: false, can_change: false }) });
  assert.equal(toggle()?.disabled, true);
  assert.match(document.body.textContent ?? "", /El dueño del negocio puede activar la lectura\./);
});

test("the other ways show only for the channels the server enables", async () => {
  const ways = () => document.querySelector<HTMLElement>('[data-testid="intake-other-ways"]');
  await mount({ email: false, whatsapp: false });
  assert.equal(ways(), null);
  await cleanups.pop()!();
  document.body.innerHTML = "";

  await mount({ email: true, whatsapp: false });
  assert.match(ways()?.textContent ?? "", /También puedes enviarlos/);
  assert.match(document.querySelector('[data-testid="intake-way-email"]')?.textContent ?? "", /Reenvíalos al correo del negocio/);
  assert.equal(document.querySelector('[data-testid="intake-forward-address"]')?.textContent, "recibos.7f3k@entrada.example");
  assert.equal(document.querySelector('[data-testid="intake-way-whatsapp"]'), null);
  await cleanups.pop()!();
  document.body.innerHTML = "";

  await mount({ email: false, whatsapp: true });
  assert.equal(document.querySelector('[data-testid="intake-way-email"]'), null, "no address is asked for or shown while email is off");
  assert.match(document.querySelector('[data-testid="intake-way-whatsapp"]')?.textContent ?? "", /Envíalos por WhatsApp/);
  await cleanups.pop()!();
  document.body.innerHTML = "";

  const both = await mount({ email: true, whatsapp: true });
  assert.ok(document.querySelector('[data-testid="intake-way-email"]') && document.querySelector('[data-testid="intake-way-whatsapp"]'));
  await both.choose(photo("a.jpg"));
  assert.equal(ways(), null, "with files in the list the panel is the list");
});
