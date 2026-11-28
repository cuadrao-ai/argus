import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import i18next from "i18next";
import { I18nextProvider } from "react-i18next";
import spanish from "@/public/locales/es-419/common.json";
import { createRoot } from "react-dom/client";
import type { BusinessCloseState } from "@/components/business-app/BusinessCloseDialog";
import BusinessTransferDialog, { type BusinessTransferView } from "@/components/business-app/BusinessTransferDialog";
import { SHEET_SNAP_SHARE } from "@/components/ui/BottomSheet";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

const WIDTHS = [1440, 390] as const;
const VIEWPORT_HEIGHT = 844;
const rosa = { grant_id: "editar-1", name: "Rosa", shown_as: "name" as const, eligible: true as const, reason: null };
const sol = { grant_id: "blocked", name: "Sol", shown_as: "name" as const, eligible: false as const, reason: "not_admin" as const };

async function mount(width: number) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: VIEWPORT_HEIGHT });
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  const i18n = i18next.createInstance(); await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  const calls: string[] = [];
  const request: BusinessTransferView = { kind: "request", businessName: "Taller Luna", members: [rosa, sol], onRequest: (id, name) => { calls.push(`request:${id}:${name}`); } };
  const render = async (view: BusinessTransferView = request, state: BusinessCloseState = { kind: "idle" }, onRefresh?: () => void) => {
    await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessTransferDialog view={view} state={state} onDismiss={() => { calls.push("dismiss"); }} onRefresh={onRefresh} /></I18nextProvider>));
  };
  await render();
  const buttons = () => [...document.querySelectorAll("button")].map((item) => item.textContent).filter(Boolean);
  const button = (text: string) => { const found = [...document.querySelectorAll("button")].find((item) => item.textContent === text); assert.ok(found, `button ${text}`); return found; };
  const enter = async (value: string) => {
    const field = document.querySelector('input:not([type="radio"])'); assert.ok(field instanceof HTMLInputElement);
    await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(field, value); field.dispatchEvent(new Event("input", { bubbles: true })); });
  };
  /** One surface, the close dialog's: centered on desktop, the shared bottom sheet below it. Never a drawer or an alert. */
  const oneDialog = () => {
    const dialogs = document.querySelectorAll('[role="dialog"]');
    assert.equal(dialogs.length, 1, "one dialog");
    assert.equal(document.querySelector('[role="alertdialog"]'), null, "no second confirm");
    assert.equal(document.querySelector('[data-testid="side-drawer"]'), null, "no side panel");
    assert.equal(Boolean(document.querySelector('[data-testid="business-close-dialog"]')), width >= 1024, "the close dialog on desktop, the sheet on a phone");
    return dialogs[0];
  };
  return { calls, render, button, buttons, enter, oneDialog, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

for (const width of WIDTHS) {
  test(`owner at ${width}: one dialog with the picker, the typed name and Solicitar, and no second step`, async () => {
    const view = await mount(width);
    try {
      const dialog = view.oneDialog();
      assert.ok(dialog.textContent?.includes("Transferir este negocio"));
      assert.ok(dialog.textContent?.includes("Nuevo dueño"));
      assert.ok(dialog.textContent?.includes("Elige un miembro del negocio. Será dueño cuando acepte."));
      assert.ok(dialog.textContent?.includes("Escribe Taller Luna para confirmar."));
      assert.equal(dialog.querySelector("label strong")?.textContent, "Taller Luna");
      assert.equal(view.button("Solicitar transferencia").disabled, true);
      await act(async () => document.querySelector<HTMLInputElement>('input[type="radio"][value="editar-1"]')!.click());
      await view.enter("Taller Luna ");
      assert.equal(view.button("Solicitar transferencia").disabled, true);
      await view.enter("Taller Luna");
      await act(async () => view.button("Solicitar transferencia").click());
      assert.deepEqual(view.calls, ["request:editar-1:Taller Luna"], "Solicitar sends the request itself");
      view.oneDialog();
      await act(async () => view.button("Cancelar").click());
      assert.deepEqual(view.calls, ["request:editar-1:Taller Luna", "dismiss"]);
    } finally { await view.close(); }
  });

  test(`recipient at ${width}: one question with Rechazar and Aceptar, and no second step`, async () => {
    const view = await mount(width);
    try {
      const recipient: BusinessTransferView = { kind: "recipient", businessName: "Taller Luna", ownerName: "Lucas", expiresAt: "2026-12-04T17:45:00Z", onAccept: () => { view.calls.push("accept"); }, onDecline: () => { view.calls.push("decline"); } };
      await view.render(recipient);
      const dialog = view.oneDialog();
      assert.equal(dialog.querySelector("h2")?.textContent, "¿Aceptar Taller Luna?");
      assert.equal(dialog.querySelector("h2 strong")?.textContent, "Taller Luna");
      assert.ok(dialog.textContent?.includes("Serás el dueño. Solo tú podrás cerrar o transferir el negocio. Lucas podrá seguir editando."));
      assert.ok(dialog.textContent?.includes("Vence 4 de diciembre de 2026"));
      await act(async () => view.button("Aceptar transferencia").click());
      assert.deepEqual(view.calls, ["accept"], "Aceptar answers at once");
      view.oneDialog();
      await act(async () => view.button("Rechazar").click());
      assert.deepEqual(view.calls, ["accept", "decline"]);
      await view.render(recipient, { kind: "submitting" });
      assert.equal(view.button("Aceptar transferencia").disabled, true);
      assert.equal(view.button("Rechazar").disabled, true);
    } finally { await view.close(); }
  });
}

test("owning another open Business is no reason: the picker has no such line and a member who owns one can be picked", async () => {
  const view = await mount(1440);
  try {
    assert.deepEqual(Object.keys(spanish.business.lifecycle.transfer.ineligible).sort(), ["account_unavailable", "email_unconfirmed", "not_admin"]);
    await view.render({ kind: "request", businessName: "Taller Luna", members: [rosa, sol], onRequest: (id) => { view.calls.push(id); } });
    assert.equal(document.body.textContent?.includes("Ya es dueño de otro negocio abierto."), false);
    assert.equal(document.querySelector<HTMLInputElement>('input[type="radio"][value="editar-1"]')!.disabled, false);
  } finally { await view.close(); }
});

test("a member who cannot receive the Business shows the reason and cannot be picked", async () => {
  const view = await mount(1440);
  try {
    const blocked = document.querySelector<HTMLInputElement>('input[type="radio"][value="blocked"]');
    assert.ok(blocked);
    assert.equal(blocked.disabled, true);
    assert.ok(document.body.textContent?.includes("Primero cambia su acceso a Administrador."));
    await act(async () => blocked.click());
    await view.enter("Taller Luna");
    assert.equal(view.button("Solicitar transferencia").disabled, true);
    assert.deepEqual(view.calls, []);
  } finally { await view.close(); }
});

test("a member who can receive the Business shows the name alone; one who cannot keeps the reason line", async () => {
  const view = await mount(1440);
  try {
    const lines = (grant: string) => [...document.querySelector(`input[value="${grant}"]`)!.closest("label")!.querySelectorAll("span > span")].map((item) => item.textContent);
    assert.deepEqual(lines("editar-1"), ["Rosa"]);
    assert.deepEqual(lines("blocked"), ["Sol", "Primero cambia su acceso a Administrador."]);
    assert.equal(document.body.textContent?.includes("Editar"), false);
  } finally { await view.close(); }
});

test("only an Administrador can be picked: the name alone; an Editor or a Lector is told to change the access first", async () => {
  const view = await mount(1440);
  try {
    const member = (grant_id: string, name: string, eligible: boolean) => ({ grant_id, name, shown_as: "name" as const, ...(eligible ? { eligible: true as const, reason: null } : { eligible: false as const, reason: "not_admin" as const }) });
    await view.render({ kind: "request", businessName: "Taller Luna", members: [member("admin", "Ana", true), member("editor", "Luis", false), member("lector", "Carla", false)], onRequest: () => undefined });
    const row = (grant: string) => { const input = document.querySelector(`input[value="${grant}"]`) as HTMLInputElement; return { disabled: input.disabled, lines: [...input.closest("label")!.querySelectorAll("span > span")].map((item) => item.textContent) }; };
    assert.deepEqual(row("admin"), { disabled: false, lines: ["Ana"] });
    assert.deepEqual(row("editor"), { disabled: true, lines: ["Luis", "Primero cambia su acceso a Administrador."] });
    assert.deepEqual(row("lector"), { disabled: true, lines: ["Carla", "Primero cambia su acceso a Administrador."] });
  } finally { await view.close(); }
});

const SHORT_VIEWS: [string, BusinessTransferView][] = [
  ["Pendiente", { kind: "pending", targetName: "Rosa", expiresAt: "2026-12-04T17:45:00Z", onWithdraw: () => undefined }],
  ["the recipient question", { kind: "recipient", businessName: "Taller Luna", ownerName: "Lucas", expiresAt: "2026-12-04T17:45:00Z", onAccept: () => undefined, onDecline: () => undefined }],
  ["the declined notice", { kind: "declined", businessName: "Taller Luna", targetName: "Rosa" }],
  ["the expired notice", { kind: "expired", targetName: "Rosa" }],
  ["the completed notice", { kind: "accepted" }],
  ["the link that did not load", { kind: "failed", of: "transfer", reference: null, onRetry: () => undefined }],
];
for (const [name, short] of SHORT_VIEWS) {
  test(`at 390 ${name} is a sheet as tall as its content, never a fixed full height`, async () => {
    const view = await mount(390);
    try {
      await view.render(short);
      const sheet = view.oneDialog() as HTMLElement;
      assert.equal(sheet.getAttribute("data-snap"), "fit", "the sheet hugs its content");
      assert.equal(sheet.style.height, "", "no fixed height");
      assert.equal(sheet.style.maxHeight, `${Math.round(VIEWPORT_HEIGHT * SHEET_SNAP_SHARE.full)}px`, "it grows only as far as the full snap, then its body scrolls");
    } finally { await view.close(); }
  });
}

test("no members says so with no picker; no eligible member lists each reason and offers no request", async () => {
  const view = await mount(1440);
  try {
    await view.render({ kind: "request", businessName: "Taller Luna", members: [], onRequest: () => { view.calls.push("request"); } });
    assert.ok(view.oneDialog().textContent?.includes("Para transferir el negocio, primero invita a un miembro."));
    assert.equal(document.querySelector("input"), null);
    assert.deepEqual(view.buttons(), []);
    await view.render({ kind: "request", businessName: "Taller Luna", members: [sol], onRequest: () => { view.calls.push("request"); } });
    const dialog = view.oneDialog();
    assert.ok(dialog.textContent?.includes("Ningún miembro puede recibir el negocio ahora. Revisa el motivo junto a cada persona."));
    assert.ok(dialog.textContent?.includes("Primero cambia su acceso a Administrador."));
    assert.equal(document.querySelector('input:not([type="radio"])'), null);
    assert.deepEqual(view.buttons(), []);
  } finally { await view.close(); }
});

test("a request that was not confirmed keeps its error, reference and selection inside the dialog", async () => {
  const view = await mount(1440);
  try {
    await act(async () => document.querySelector<HTMLInputElement>('input[type="radio"][value="editar-1"]')!.click());
    await view.enter("Taller Luna");
    await view.render(undefined, { kind: "submitting" });
    assert.equal(view.button("Solicitar transferencia").disabled, true);
    await view.render(undefined, { kind: "error", message: "No pudimos confirmar la solicitud.", reference: "b195f748-16ea-4b93-a9b0-f139c47e77f5" });
    const dialog = view.oneDialog();
    assert.ok(dialog.querySelector('[role="alert"]')?.textContent?.includes("No pudimos confirmar la solicitud."));
    assert.ok(dialog.querySelector('[role="alert"] [data-testid="error-reference"]'));
    assert.equal(document.querySelector<HTMLInputElement>('input[type="radio"][value="editar-1"]')!.checked, true);
    await act(async () => view.button("Solicitar transferencia").click());
    assert.deepEqual(view.calls, ["request:editar-1:Taller Luna"]);
  } finally { await view.close(); }
});

test("pending shows who is awaited, the expiry line and Retirar solicitud", async () => {
  const view = await mount(390);
  try {
    await view.render({ kind: "pending", targetName: "Rosa", expiresAt: "2026-12-04T17:45:00Z", onWithdraw: () => { view.calls.push("withdraw"); } });
    const dialog = view.oneDialog();
    assert.ok(dialog.textContent?.includes("Transferir este negocio"));
    assert.ok(dialog.textContent?.includes("Esperando que Rosa acepte."));
    assert.ok(dialog.textContent?.includes("Vence 4 de diciembre de 2026"));
    assert.deepEqual(view.buttons(), ["Retirar solicitud"]);
    await act(async () => view.button("Retirar solicitud").click());
    assert.deepEqual(view.calls, ["withdraw"]);
  } finally { await view.close(); }
});

test("accept not confirmed: its sentence and reference stay in the dialog with Actualizar alone", async () => {
  const view = await mount(1440);
  try {
    const recipient: BusinessTransferView = { kind: "recipient", businessName: "Taller Luna", ownerName: "Lucas", onAccept: () => { view.calls.push("accept"); }, onDecline: () => { view.calls.push("decline"); } };
    await view.render(recipient, { kind: "error", message: spanish.business.lifecycle.errors.accept_uncertain, reference: "4ea79978-ce17-4853-b232-b2a72f4c9ce7" }, () => { view.calls.push("refresh"); });
    const dialog = view.oneDialog();
    assert.equal(dialog.querySelector("h2")?.textContent, "¿Aceptar Taller Luna?");
    assert.ok(dialog.querySelector('[role="alert"]')?.textContent?.includes("No pudimos confirmar la aceptación. Actualiza para comprobar el resultado."));
    assert.ok(dialog.querySelector('[role="alert"] [data-testid="error-reference"]'));
    assert.deepEqual(view.buttons().filter((label) => !label?.startsWith("Ref.")), ["Actualizar"]);
    await act(async () => view.button("Actualizar").click());
    assert.deepEqual(view.calls, ["refresh"]);
  } finally { await view.close(); }
});

const NOTICES: [string, BusinessTransferView, string, "status" | "alert", string[]][] = [
  ["the recipient declined", { kind: "declined", businessName: "Taller Luna", targetName: "Rosa" }, "Rosa rechazó la transferencia. Taller Luna sigue siendo tuyo.", "status", []],
  ["the request expired", { kind: "expired", targetName: "Rosa" }, "La solicitud a Rosa venció.", "status", []],
  ["the transfer completed", { kind: "accepted" }, "Transferencia completada", "status", []],
  ["the request was withdrawn", { kind: "cancelled" }, "Transferencia retirada", "status", []],
  ["the recipient had declined", { kind: "declinedRecipient" }, "Transferencia rechazada", "status", []],
  ["the link is not available", { kind: "unavailable", of: "transfer" }, "Esta transferencia no está disponible con tu acceso actual.", "alert", []],
  ["the link expired", { kind: "expiredLink" }, "Esta solicitud venció.", "alert", []],
  ["the link did not load", { kind: "failed", of: "transfer", reference: null, onRetry: () => undefined }, "No pudimos cargar la transferencia. Intenta otra vez.", "alert", ["Reintentar"]],
  ["the Business is not the person's", { kind: "unavailable", of: "business" }, "Este negocio no está disponible con tu acceso actual.", "alert", []],
  ["the Businesses did not load", { kind: "failed", of: "business", reference: null, onRetry: () => undefined }, "No pudimos cargar tus negocios. Intenta otra vez.", "alert", ["Reintentar"]],
];
for (const [name, notice, words, role, actions] of NOTICES) {
  test(`${name}: the same dialog says it in the existing words`, async () => {
    const view = await mount(1440);
    try {
      await view.render(notice);
      const dialog = view.oneDialog();
      assert.equal(dialog.querySelector("h2")?.textContent, "Transferir este negocio");
      assert.equal(dialog.querySelector(`[role="${role}"]`)?.textContent, words);
      assert.deepEqual(view.buttons(), actions);
    } finally { await view.close(); }
  });
}

test("loading waits in the same dialog", async () => {
  const view = await mount(390);
  try {
    await view.render({ kind: "loading" });
    assert.equal(view.oneDialog().querySelector('[role="status"]')?.textContent, "Cargando...");
    assert.deepEqual(view.buttons(), []);
  } finally { await view.close(); }
});
