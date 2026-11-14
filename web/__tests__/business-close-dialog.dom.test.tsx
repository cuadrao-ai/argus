import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import spanish from "@/public/locales/es-419/common.json";
import english from "@/public/locales/en/common.json";
import { createRoot } from "react-dom/client";
import BusinessCloseDialog, { businessCloseCopyEs, type BusinessCloseState, type CloseDownload } from "@/components/business-app/BusinessCloseDialog";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

const windows = [
  { key: "2025-01-01/2025-12-31", start: "2025-01-01", end: "2025-12-31", record_count: 1204, status: "idle" },
  { key: "2026-01-01/2026-10-21", start: "2026-01-01", end: "2026-10-21", record_count: 1, status: "idle" },
] satisfies CloseDownload[];

async function mount(first: CloseDownload[] = windows, members = 7) {
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const confirmed: string[] = [];
  const started: (string | undefined)[] = [];
  let cancelled = 0;
  let items = first;
  const render = async (state: BusinessCloseState = { kind: "idle" }, name = "Taller Luna", next = items) => {
    items = next;
    await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessCloseDialog businessName={name} preview={{ member_count: members, reopen_until: "2026-11-20T17:45:00Z" }} copy={businessCloseCopyEs} state={state} downloads={{ items, start: (key) => { started.push(key); } }} onConfirm={(name) => { confirmed.push(name); }} onCancel={() => { cancelled++; }} /></I18nextProvider>));
  };
  await render();
  const button = (text: string) => { const found = [...document.querySelectorAll("button")].find((item) => item.textContent === text); assert.ok(found, text); return found; };
  const enter = async (value: string) => { const input = document.querySelector("input"); assert.ok(input); await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value); input.dispatchEvent(new Event("input", { bubbles: true })); }); };
  const openConfirm = () => act(async () => button(items.every((item) => item.status === "downloaded") ? businessCloseCopyEs.continue : businessCloseCopyEs.continueWithout).click());
  return { confirmed, started, render, button, enter, openConfirm, cancelled: () => cancelled, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}
const text = () => document.body.textContent ?? "";

test("closing is one centered dialog, never the side dossier or a second overlay", async () => {
  const view = await mount();
  try {
    const dialog = document.querySelector('[data-testid="business-close-dialog"]');
    assert.ok(dialog);
    assert.equal(dialog.getAttribute("role"), "dialog");
    assert.equal(dialog.getAttribute("aria-modal"), "true");
    assert.equal(document.querySelector("h2")?.textContent, "Cerrar Taller Luna");
    assert.ok(text().includes("Al cerrar, tendrás 30 días para reabrir este negocio. Después, se borra y no se puede recuperar. Descarga una copia antes de continuar."));
    assert.ok(text().includes("La copia incluye tus registros en Excel y CSV y, cuando es posible, el archivo de cada documento."));
    assert.ok(view.button("Descargar copia") && view.button("Continuar sin descargar"));
    await view.openConfirm();
    assert.equal(document.querySelectorAll('[aria-modal="true"]').length, 1);
    assert.equal(document.querySelector('[data-testid="business-close-dialog"]'), dialog, "the confirm is a step inside the same dialog");
    assert.equal(document.querySelector("h2")?.textContent, "¿Cerrar Taller Luna?");
    assert.equal(document.querySelector("label")?.textContent, "Escribe Taller Luna para confirmar.");
    assert.equal(/ley|10 años|borramos/.test(text()), false, "no legal text and no promised deletion");
    await act(async () => view.button(businessCloseCopyEs.cancel).click());
    assert.equal(view.cancelled(), 0, "Cancelar returns to the downloads");
    assert.ok(text().includes(businessCloseCopyEs.warning));
    const dismiss = document.querySelector<HTMLButtonElement>(`button[aria-label="${businessCloseCopyEs.cancel}"]`);
    assert.ok(dismiss);
    await act(async () => dismiss.click());
    assert.equal(view.cancelled(), 1);
  } finally { await view.close(); }
});

test("each period reads as a range of months with the server's counts, never an ISO date", async () => {
  const view = await mount();
  try {
    const rows = [...document.querySelectorAll('[data-testid="business-close-period"]')].map((row) => row.textContent ?? "");
    assert.equal(rows.length, 2);
    assert.ok(rows[0].startsWith("ene – dic 2025 · 1,204 registros"), rows[0]);
    assert.ok(rows[1].startsWith("ene – 21 oct 2026 · 1 registro") && !rows[1].includes("1 registros"), rows[1]);
    assert.equal(/original/i.test(text()), false, "no count of original files");
    assert.equal(/\d{4}-\d{2}-\d{2}/.test(text()), false);
  } finally { await view.close(); }
});

test("the main action downloads what is left, each period shows its state, and the last step is the red confirm", async () => {
  const view = await mount();
  try {
    assert.ok(view.button(businessCloseCopyEs.download).className.includes("bg-[var(--cuadrao-green)]"));
    await act(async () => view.button(businessCloseCopyEs.download).click());
    assert.deepEqual(view.started, [undefined]);
    await view.render({ kind: "idle" }, "Taller Luna", [{ ...windows[0], status: "downloaded" }, windows[1]]);
    const rows = [...document.querySelectorAll('[data-testid="business-close-period"]')];
    assert.equal(rows[0].getAttribute("data-status"), "downloaded");
    assert.ok(rows[0].textContent?.includes("Descargado"));
    assert.equal(rows[1].getAttribute("data-status"), "idle");
    assert.equal(rows[1].textContent?.includes("Descargado"), false);
    await act(async () => rows[1].querySelector("button")!.click());
    assert.deepEqual(view.started, [undefined, windows[1].key]);
    await view.openConfirm();
    assert.equal(view.button(businessCloseCopyEs.close).disabled, true);
    await act(async () => view.button(businessCloseCopyEs.cancel).click());
    await view.render({ kind: "idle" }, "Taller Luna", windows.map((item) => ({ ...item, status: "downloaded" as const })));
    assert.equal([...document.querySelectorAll("button")].some((item) => item.textContent === businessCloseCopyEs.continueWithout), false);
    assert.ok(view.button(businessCloseCopyEs.continue).className.includes("bg-[var(--cuadrao-green)]"));
    await view.openConfirm();
    assert.deepEqual(view.confirmed, []);
  } finally { await view.close(); }
});

test("a Business with no history has nothing to download and goes straight on", async () => {
  const view = await mount([]);
  try {
    assert.ok(text().includes("No hay registros ni comprobantes para descargar."));
    assert.equal([...document.querySelectorAll("button")].some((item) => item.textContent === businessCloseCopyEs.download), false);
    await act(async () => view.button(businessCloseCopyEs.continue).click());
    assert.ok(text().includes("Escribe Taller Luna para confirmar."));
  } finally { await view.close(); }
});

test("close requires the exact current name without trimming or case folding", async () => {
  const view = await mount();
  try {
    await view.openConfirm();
    assert.equal(view.button(businessCloseCopyEs.close).disabled, true);
    for (const name of ["Taller", "taller luna", "Taller Luna "]) {
      await view.enter(name);
      assert.equal(view.button(businessCloseCopyEs.close).disabled, true);
    }
    await view.enter("Taller Luna");
    assert.equal(view.button(businessCloseCopyEs.close).disabled, false);
    await act(async () => view.button(businessCloseCopyEs.close).click());
    assert.deepEqual(view.confirmed, ["Taller Luna"]);
    await view.render({ kind: "idle" }, "Taller Sol");
    assert.equal(view.button(businessCloseCopyEs.close).disabled, true);
  } finally { await view.close(); }
});

test("submitting blocks repeated close and cancellation while errors preserve the name", async () => {
  const view = await mount();
  try {
    await view.openConfirm();
    await view.enter("Taller Luna");
    await view.render({ kind: "submitting" });
    assert.equal(view.button(businessCloseCopyEs.close).disabled, true);
    assert.equal(view.button(businessCloseCopyEs.cancel).disabled, true);
    await view.render({ kind: "error", message: "fixture error" });
    assert.equal(document.querySelector("input")?.value, "Taller Luna");
    assert.equal(document.querySelector('[role="alert"]')?.textContent, "fixture error");
    assert.equal(view.button(businessCloseCopyEs.close).disabled, false);
  } finally { await view.close(); }
});


test("close uses readable destructive colors in light and dark modes", async () => {
  const view = await mount();
  const luminance = (hex: string) => {
    const rgb = hex.match(/../g)!.map((part) => parseInt(part, 16) / 255).map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
    return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
  };
  try {
    await view.openConfirm();
    await view.enter("Taller Luna");
    const classes = view.button(businessCloseCopyEs.close).className;
    const light = classes.match(/(?:^| )bg-\[#([0-9a-f]{6})\]/);
    const dark = classes.match(/dark:bg-\[#([0-9a-f]{6})\]/);
    assert.ok(light && dark);
    assert.ok(classes.split(" ").includes("text-white"));
    const darkForeground = classes.match(/dark:text-\[#([0-9a-f]{6})\]/);
    assert.ok(darkForeground);
    const contrast = (foreground: string, background: string) => {
      const values = [luminance(foreground), luminance(background)].sort((a, b) => a - b);
      return (values[1] + 0.05) / (values[0] + 0.05);
    };
    assert.ok(contrast("ffffff", light[1]) >= 4.5);
    assert.ok(contrast(darkForeground[1], dark[1]) >= 4.5);
  } finally { await view.close(); }
});


test("close confirmation uses the server member count and the server's reopen date, with no time", async () => {
  const view = await mount();
  try {
    await view.openConfirm();
    assert.ok(text().includes("7 miembros pierden acceso al cerrar."));
    assert.ok(text().includes("Podrás reabrirlo hasta el 20 de noviembre de 2026."));
    assert.equal(/hora de RD|\d{1,2}:\d{2}/.test(text()), false);
    assert.deepEqual(view.confirmed, []);
  } finally { await view.close(); }
});

for (const [members, line] of [[0, null], [1, "1 miembro pierde acceso al cerrar."], [2, "2 miembros pierden acceso al cerrar."]] as const) {
  test(`the member line ${line ? "shows" : "is hidden"} with ${members} members`, async () => {
    const view = await mount(windows, members);
    try {
      await view.openConfirm();
      assert.equal(document.querySelector('[data-testid="business-close-members"]')?.textContent ?? null, line);
      assert.equal(/pierden? acceso/.test(text()), line !== null);
      assert.ok(text().includes("Podrás reabrirlo hasta el"));
    } finally { await view.close(); }
  });
}

test("the locked copy is in both locales and the retired keys are gone", () => {
  const locked = {
    "close.title_named": ["Cerrar {{businessName}}", "Close {{businessName}}"],
    "close.warning": ["Al cerrar, tendrás 30 días para reabrir este negocio. Después, se borra y no se puede recuperar. Descarga una copia antes de continuar.", "After you close, you have 30 days to reopen this business. After that, it's deleted and can't be recovered. Download a copy before you continue."],
    "export.package": ["La copia incluye tus registros en Excel y CSV y, cuando es posible, el archivo de cada documento.", "The copy includes your records in Excel and CSV and, when possible, the file for each document."],
    "close.download": ["Descargar copia", "Download copy"],
    "close.continue_without": ["Continuar sin descargar", "Continue without downloading"],
    "close_alert_title": ["¿Cerrar {{businessName}}?", "Close {{businessName}}?"],
    "close_preview.member_count_other": ["{{count}} miembros pierden acceso al cerrar.", "{{count}} members lose access when you close."],
    "close_preview.reopen_until": ["Podrás reabrirlo hasta el {{purgeDate}}.", "You can reopen it until {{purgeDate}}."],
    "close.confirmation": ["Escribe {{businessName}} para confirmar.", "Type {{businessName}} to confirm."],
    "close.action": ["Cerrar negocio", "Close business"],
  };
  const read = (root: unknown, path: string) => path.split(".").reduce<unknown>((node, key) => (node as Record<string, unknown> | undefined)?.[key], root);
  for (const [path, [es, en]] of Object.entries(locked)) {
    assert.equal(read(spanish.business.lifecycle, path), es, path);
    assert.equal(read(english.business.lifecycle, path), en, path);
  }
  assert.equal(spanish.common.cancel, "Cancelar");
  for (const lifecycle of [spanish.business.lifecycle, english.business.lifecycle]) {
    for (const gone of ["close.consequences", "close.missing_one", "close.missing_other", "close_preview.member_count_zero", "export.complete", "export.originals_one", "export.originals_other"]) assert.equal(read(lifecycle, gone), undefined, gone);
  }
});
