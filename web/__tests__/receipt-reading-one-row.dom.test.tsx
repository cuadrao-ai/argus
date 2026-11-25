import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import { BusinessContext, type BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import { BusinessConsentTestProvider } from "@/components/business-app/business-consent-context";
import ReceiptReadingControl from "@/components/business-app/ReceiptReadingControl";
import { fixtureReceiptReading } from "@/components/business-app/fixture-data";
import type { ReceiptReading } from "@/lib/business-api";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";

const WORDS = "Permiso del servidor para leer documentos.";
const cleanups: (() => Promise<void>)[] = [];

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", { configurable: true, writable: true, value: true });
});
afterEach(async () => { while (cleanups.length) await cleanups.pop()!(); document.body.innerHTML = ""; });
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function mount(read: Partial<ReceiptReading> | null, variant: "notice" | "inline" = "notice", save?: (enabled: boolean) => Promise<void>) {
  const sent: { enabled: boolean; token: string | null; version: number }[] = [];
  const context = {
    source: {
      setReceiptReading: async (current: ReceiptReading, enabled: boolean) => {
        sent.push({ enabled, token: current.disclosure_token, version: current.scope_version });
        await save?.(enabled);
        return { ...current, enabled, consented_at: enabled ? "2026-11-23T12:00:00Z" : current.consented_at };
      },
    },
    chosen: { space_id: "own" },
    records: { workspace: { receipt_reading: read && fixtureReceiptReading({ disclosure: WORDS, ...read }) }, workspaceGrant: null, workspaceRevision: 0 },
    revision: 0, reload() {},
  } as unknown as BusinessContextValue;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const host = document.body.appendChild(document.createElement("div"));
  const root = createRoot(host);
  await act(async () => root.render(
    <I18nextProvider i18n={i18n}><BusinessConsentTestProvider accepted><BusinessContext.Provider value={context}>
      <ReceiptReadingControl variant={variant} />
    </BusinessContext.Provider></BusinessConsentTestProvider></I18nextProvider>,
  ));
  cleanups.push(async () => { await act(async () => root.unmount()); host.remove(); });
  const notice = () => host.querySelector<HTMLElement>('[data-testid="receipt-reading-notice"]');
  const click = (button: HTMLElement | null | undefined) => act(async () => { assert.ok(button); button.click(); for (let i = 0; i < 6; i += 1) await Promise.resolve(); });
  return {
    host, sent, notice, click,
    turnOn: () => host.querySelector<HTMLButtonElement>('[data-testid="receipt-reading-turn-on"]'),
    toggle: () => host.querySelector<HTMLButtonElement>('[role="switch"]'),
    dialog: () => document.querySelector<HTMLElement>('[role="alertdialog"]'),
  };
}

test("reading off is a compact notice: it says reading is off, the short line, and one button beside the text, never a switch", async () => {
  const page = await mount({ enabled: false });
  const notice = page.notice()!;
  assert.deepEqual([...notice.querySelectorAll("span > span")].map((line) => line.textContent), ["La lectura automática está apagada.", "Tú siempre revisas y aceptas."]);
  assert.equal(page.turnOn()?.textContent, "Activar lectura de documentos");
  assert.equal(page.turnOn()?.previousElementSibling, notice.querySelector("span"), "the button sits right beside the text");
  assert.doesNotMatch(page.turnOn()!.parentElement!.className, /justify-between/);
  assert.ok(page.turnOn()!.parentElement!.classList.contains("gap-x-4"));
  assert.equal(page.toggle(), null, "no switch");
  assert.equal(page.host.querySelector('[data-testid="receipt-reading-control"]'), null, "the switch row belongs to the upload panel");
  assert.equal(notice.textContent?.includes(WORDS), false);
  assert.deepEqual([...notice.querySelectorAll("button")], [page.turnOn()], "the button is the notice's only control");
});

test("reading on, or a setting the server did not answer, shows no notice", async () => {
  for (const read of [{ enabled: true }, null]) {
    const page = await mount(read);
    assert.equal(page.notice(), null);
    assert.equal(page.turnOn(), null);
    assert.equal(page.toggle(), null);
    await cleanups.pop()!();
  }
});

test("the first turn-on confirms the server disclosure in a modal and waits for the save", async () => {
  let finish!: () => void;
  const pending = new Promise<void>((resolve) => { finish = resolve; });
  const page = await mount({ enabled: false, consented_at: null, disclosure_token: "f".repeat(64), scope_version: 3 }, "notice", () => pending);
  const notice = page.notice()!;
  const atRest = notice.innerHTML;
  await page.click(page.turnOn());
  assert.deepEqual(page.sent, []);
  assert.equal(notice.innerHTML, atRest);
  const dialog = page.dialog()!;
  assert.equal(dialog.getAttribute("aria-modal"), "true");
  assert.equal(dialog.querySelector("h2")?.textContent, "Leer mis documentos automáticamente");
  assert.equal(dialog.querySelector("p")?.textContent, WORDS);
  const [cancel, confirm] = dialog.querySelectorAll("button");
  assert.deepEqual([cancel.textContent, confirm.textContent], ["Cancelar", "Confirmar"]);
  assert.equal(document.activeElement, cancel);
  await page.click(confirm);
  assert.ok(confirm.disabled && cancel.disabled);
  assert.equal(confirm.getAttribute("aria-busy"), "true");
  assert.deepEqual(page.sent, [{ enabled: true, token: "f".repeat(64), version: 3 }]);
  await act(async () => finish());
  assert.equal(page.notice(), null);
  assert.equal(page.dialog(), null);
});

test("cancel, Escape and the scrim close first-time consent and restore focus without saving", async () => {
  const page = await mount({ enabled: false });
  const opener = page.turnOn()!;
  for (const action of ["cancel", "escape", "scrim"]) {
    await page.click(opener);
    const dialog = page.dialog()!;
    if (action === "escape") {
      await act(async () => { document.activeElement!.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
    } else {
      await page.click(action === "cancel" ? dialog.querySelector("button") : dialog.parentElement!.querySelector("button[tabindex='-1']"));
    }
    assert.equal(page.dialog(), null, action);
    assert.equal(document.activeElement, opener, action);
    assert.deepEqual(page.sent, []);
  }
});

test("a failed first consent offers retry inside the dark dialog", async () => {
  document.documentElement.classList.add("dark");
  try {
    let refuse = true;
    const page = await mount({ enabled: false }, "notice", async () => { if (refuse) throw new Error("refused"); });
    await page.click(page.turnOn());
    const dialog = page.dialog()!;
    assert.match(dialog.className, /dark:bg-|var\(--/);
    assert.match(dialog.querySelector("p")!.className, /dark:text-|var\(--/);
    assert.match(dialog.querySelector("button")!.className, /dark:text-|var\(--/);
    const confirm = dialog.querySelector<HTMLButtonElement>('[data-testid="confirm-dialog-confirm"]')!;
    await page.click(confirm);
    assert.match(dialog.querySelector('[role="alert"]')?.textContent ?? "", /No se pudo actualizar/);
    assert.equal(page.notice()?.querySelector('[role="alert"]'), null);
    assert.equal(confirm.textContent, "Reintentar");
    refuse = false;
    await page.click(confirm);
    assert.deepEqual(page.sent.map((call) => call.enabled), [true, true]);
    assert.equal(page.dialog(), null);
    assert.equal(page.notice(), null);
  } finally { document.documentElement.classList.remove("dark"); }
});

test("a Business that accepted before turns reading on in place, with no paragraph", async () => {
  const page = await mount({ enabled: false, consented_at: "2026-11-01T12:00:00Z", revoked_at: "2026-11-10T12:00:00Z", disclosure_token: "e".repeat(64), scope_version: 3 });
  await page.click(page.turnOn());
  assert.deepEqual(page.sent, [{ enabled: true, token: "e".repeat(64), version: 3 }], "the same server call and token as the first time");
  assert.equal(page.host.textContent?.includes(WORDS), false);
  assert.equal(page.dialog(), null);
  assert.equal(page.notice(), null);
});

test("a turn-on the server refuses keeps the notice, off, with the error and a retry", async () => {
  let refuse = true;
  const page = await mount({ enabled: false, consented_at: "2026-11-01T12:00:00Z" }, "notice", async () => { if (refuse) throw new Error("refused"); });
  await page.click(page.turnOn());
  assert.equal(page.dialog(), null);
  assert.equal(page.turnOn()?.disabled, false, "the button is ready again");
  const alert = page.notice()!.querySelector('[role="alert"]')!;
  assert.match(alert.textContent ?? "", /No se pudo actualizar la lectura de documentos\./);
  refuse = false;
  await page.click(alert.querySelector("button"));
  assert.deepEqual(page.sent.map((call) => call.enabled), [true, true]);
  assert.equal(page.notice(), null);
});

test("someone who cannot change the setting sees the notice say who can, with the button locked", async () => {
  const page = await mount({ enabled: false, can_change: false });
  assert.equal(page.turnOn()?.disabled, true);
  assert.match(page.notice()!.textContent ?? "", /El dueño del negocio puede activar la lectura\./);
});

test("Ajustes keeps the switch beside the full paragraph, and it is where reading turns off", async () => {
  const page = await mount({ enabled: true, consented_at: "2026-11-01T12:00:00Z" }, "inline");
  const card = page.host.querySelector<HTMLElement>('[data-testid="receipt-reading-inline"]')!;
  assert.equal(card.querySelector("h2")?.textContent, "Leer mis documentos automáticamente");
  assert.ok(card.textContent?.includes(WORDS));
  assert.equal(page.toggle()?.getAttribute("aria-checked"), "true");
  await page.click(page.toggle());
  assert.deepEqual(page.sent.map((call) => call.enabled), [false]);
  assert.equal(page.toggle()?.getAttribute("aria-checked"), "false");
  assert.ok(card.textContent?.includes(WORDS), "the paragraph stays in Ajustes");
});

const WEB = join(import.meta.dir, "..");
function sources(folder: string): string[] {
  return readdirSync(join(WEB, folder), { withFileTypes: true }).flatMap((entry) => {
    const path = join(folder, entry.name);
    if (entry.isDirectory()) return entry.name === "node_modules" ? [] : sources(path);
    return /\.(ts|tsx|css)$/.test(entry.name) ? [path] : [];
  });
}

test("no reading sheet, no button that opens one and no second title is left in the app", () => {
  const retired = /ReadingSheet|ReadingRow|receipt-reading-sheet|receipt-reading-row|activity\.sheet_title|activity\.turn_on|reception\.reading_title|sheetOpen/;
  const found = ["components", "app", "lib"].flatMap(sources).filter((path) => retired.test(readFileSync(join(WEB, path), "utf8")));
  assert.deepEqual(found, []);
  for (const [language, words] of [["es-419", spanish], ["en", english]] as const) {
    const activity = words.business.activity as Record<string, string>;
    for (const key of ["sheet_title", "turn_on", "change", "saved_prompt", "state_on", "state_off", "turned_off"]) assert.equal(key in activity, false, `${language} business.activity.${key}`);
    assert.equal("reading_title" in (words.business.reception as Record<string, unknown>), false, `${language} business.reception.reading_title`);
    assert.equal("reading_help_off" in (words.business.intake as Record<string, unknown>), false, `${language} business.intake.reading_help_off`);
    assert.match(words.business.review.reading_off, /^(Activa la lectura y vuelve a intentarlo\.|Turn on reading and try again\.)$/, "the error says only to turn reading on; the row is already on screen");
  }
});
