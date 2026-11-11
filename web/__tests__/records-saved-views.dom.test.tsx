import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { I18nextProvider } from "react-i18next";
import { keepOwnListSearch } from "./fixtures/own-list-search";
import { mountConnectedReport as mount, unmountConnectedReport as cleanup } from "./support/business-reports-connected";
import { translate } from "./support/i18n-instance";

await keepOwnListSearch();

type Page = Awaited<ReturnType<typeof mount>>;
type Recipe = { filters: { q: string } & Record<string, unknown> } & Record<string, unknown>;

const originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
let unmountToasts = async () => {};
beforeAll(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; GlobalRegistrator.register({ url: "http://localhost/biz", width: 1440, height: 900 }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterEach(async () => { await unmountToasts(); (await import("@/components/business-app/foundation/toasts")).clearToasts(); await cleanup(); (await import("@/components/layout/overlayStack")).resetOverlayStack(); document.body.innerHTML = ""; (window as unknown as { happyDOM: { setURL: (url: string) => void } }).happyDOM.setURL("http://localhost/biz"); });
afterAll(async () => { await GlobalRegistrator.unregister(); if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock; });

const menu = () => document.querySelector<HTMLElement>('[role="dialog"][aria-label="Vistas"]');
const trigger = () => [...document.querySelectorAll<HTMLButtonElement>('button[aria-haspopup="dialog"]')].find((button) => button.textContent === "Vistas" || button.getAttribute("aria-label")?.startsWith("Vistas: "));
const inMenu = (label: string) => [...(menu()?.querySelectorAll("button") ?? [])].find((button) => button.textContent?.trim() === label || button.getAttribute("aria-label") === label);
const row = (name: string) => inMenu(name)?.closest("li") ?? null;
const nameField = () => menu()?.querySelector<HTMLInputElement>('input[aria-label="Nombre de la vista"]') ?? null;

async function openMenu(page: Page) {
  if (!menu()) await page.click(trigger());
  assert.ok(menu(), "the views menu is open");
}
async function closeMenu(page: Page) {
  if (menu()) await page.click(trigger());
}
/** Enter in a one-field form submits it; happy-dom has no implicit submission, so the test asks the form directly. */
async function pressEnter(field: HTMLInputElement) {
  await act(async () => field.form!.requestSubmit());
}
async function pressEscape(field: HTMLElement) {
  await act(async () => { field.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
}
async function saveView(page: Page, name: string) {
  await openMenu(page);
  await page.click(inMenu("Guardar vista actual") ?? inMenu("Guardar como vista nueva"));
  const field = nameField()!;
  await page.type(field, name);
  await pressEnter(field);
  await page.settle(() => page.fixture.views.some((view) => view.name === name) && !menu());
  return page.fixture.views.find((view) => view.name === name)!;
}
async function search(page: Page, query: string) {
  await page.type(document.querySelector<HTMLInputElement>('input[type="search"]')!, query);
  await page.settle(() => page.fixture.calls.some((call) => call.path.endsWith("/reports/query") && (call.body as { filters: { q: string } }).filters.q === query));
}
async function mountToasts() {
  const { createRoot } = await import("react-dom/client");
  const { ToastViewport } = await import("@/components/business-app/foundation/ToastViewport");
  const host = document.createElement("div"); document.body.appendChild(host);
  const root = createRoot(host);
  const i18n = await translate("es-419");
  await act(async () => root.render(<I18nextProvider i18n={i18n}><ToastViewport /></I18nextProvider>));
  unmountToasts = async () => { await act(async () => root.unmount()); unmountToasts = async () => {}; };
}
const viewWrites = (page: Page, method: string) => page.fixture.calls.filter((call) => call.method === method && call.path.includes("/report-views"));

test("the toolbar button shows the applied view's name, and loses it when the view is gone", async () => {
  const page = await mount();
  assert.equal(trigger()!.textContent, "Vistas");
  await saveView(page, "Mi vista");
  assert.equal(trigger()!.getAttribute("aria-label"), "Vistas: Mi vista");
  assert.equal(trigger()!.textContent, "Mi vista");
  await saveView(page, "Otra vista");
  assert.equal(trigger()!.textContent, "Otra vista");
  await openMenu(page);
  await page.click(inMenu("Mi vista"));
  assert.equal(trigger()!.textContent, "Mi vista");
  await openMenu(page);
  assert.equal(inMenu("Mi vista")!.getAttribute("aria-current"), "true");
  assert.equal(inMenu("Otra vista")!.getAttribute("aria-current"), null);
  await page.click(inMenu("Eliminar Mi vista"));
  await page.settle(() => page.fixture.views.length === 1);
  assert.equal(trigger()!.textContent, "Vistas");
  assert.equal(trigger()!.getAttribute("aria-label"), null);
});

test("each row keeps rename and delete reachable: shown on hover, focus within, or a device without hover", async () => {
  const page = await mount();
  await saveView(page, "Mi vista");
  await saveView(page, "Otra vista");
  await openMenu(page);
  for (const name of ["Mi vista", "Otra vista"]) {
    const rename = inMenu(`Renombrar ${name}`)!, remove = inMenu(`Eliminar ${name}`)!;
    assert.ok(rename && remove, `${name} has both actions, named for the view`);
    assert.equal(rename.closest("li"), row(name)); assert.equal(remove.closest("li"), row(name));
    assert.equal(rename.parentElement!.closest("[inert], [hidden], [aria-hidden='true']"), null, "assistive tech always reaches them");
    assert.ok(rename.parentElement!.classList.contains("rowActions"));
    await act(async () => rename.focus());
    assert.equal(document.activeElement, rename);
  }
  const rules = readFileSync(join(import.meta.dir, "../components/sidebar/pointerAffordances.module.css"), "utf8").replace(/\s+/g, " ");
  const fine = rules.slice(rules.indexOf("(hover: hover) and (pointer: fine)"), rules.indexOf("(any-pointer: coarse)"));
  const coarse = rules.slice(rules.indexOf("(any-pointer: coarse)"));
  assert.match(rules, /^[^@]*\.rowActions \{ opacity: 1; \}/, "shown by default, as on a device without hover");
  assert.match(fine, /\.rowActions \{ opacity: 0; \}/, "a mouse hides them by opacity only, so focus still lands");
  assert.match(fine, /:global\(\.group:hover\) \.rowActions, :global\(\.group:focus-within\) \.rowActions \{ opacity: 1; \}/, "hover or focus in the row shows them");
  assert.match(coarse, /\.rowActions \{ opacity: 1; \}/, "any touch input keeps them shown");
});

test("rename happens in the row: Enter saves the name only, Escape cancels to the row, a duplicate says so under it", async () => {
  const page = await mount();
  const saved = await saveView(page, "Mi vista");
  await saveView(page, "Otra vista");
  await search(page, "pena");
  await openMenu(page);
  await page.click(inMenu("Renombrar Mi vista"));
  let field = nameField()!;
  assert.equal(field.value, "Mi vista");
  assert.equal(field.closest("li"), row("Guardar nombre"), "the field replaces the row");
  assert.equal(inMenu("Guardar como vista nueva")!.disabled, true, "the footer waits while a row is renamed");

  await page.type(field, "otra VISTA");
  const alert = menu()!.querySelector('[role="alert"]');
  assert.equal(alert?.textContent, "Ya tienes una vista con este nombre.");
  assert.equal(alert!.closest("li"), field.closest("li"), "the error sits under the row being renamed");
  assert.equal(inMenu("Guardar nombre")!.disabled, true);
  await pressEnter(field);
  assert.equal(viewWrites(page, "PATCH").length, 0);

  await pressEscape(field);
  assert.ok(menu(), "Escape cancels the rename, not the menu");
  assert.equal(nameField(), null);
  assert.equal(document.activeElement, inMenu("Mi vista"));
  assert.equal(viewWrites(page, "PATCH").length, 0);

  await page.click(inMenu("Renombrar Mi vista"));
  field = nameField()!;
  await page.type(field, "Mi vista nueva");
  await pressEnter(field);
  await page.settle(() => page.fixture.views.some((view) => view.name === "Mi vista nueva"));
  const [write] = viewWrites(page, "PATCH");
  assert.deepEqual(write.body, { name: "Mi vista nueva", recipe: saved.recipe, expected_version: 1 }, "rename keeps the saved recipe, not the search typed since");
  assert.ok(menu());
  assert.equal(nameField(), null);
  assert.equal(document.activeElement, inMenu("Mi vista nueva"));
});

test("delete asks nothing, and Deshacer recreates the view with its name and recipe", async () => {
  await mountToasts();
  const page = await mount();
  const saved = await saveView(page, "Mi vista");
  await search(page, "pena");
  await openMenu(page);
  await page.click(inMenu("Eliminar Mi vista"));
  await page.settle(() => page.fixture.views.length === 0);
  assert.equal(viewWrites(page, "DELETE").length, 1);
  assert.equal(row("Mi vista"), null);
  const toast = document.querySelector('[data-testid="toast-viewport"] [role="status"]');
  assert.match(toast?.textContent ?? "", /Se eliminó «Mi vista»/);
  const undo = [...toast!.querySelectorAll("button")].find((button) => button.textContent === "Deshacer");
  await page.click(undo);
  await page.settle(() => page.fixture.views.length === 1);
  const [restored] = page.fixture.views;
  assert.equal(restored.name, "Mi vista");
  assert.deepEqual(restored.recipe, saved.recipe, "the recipe it had, not the search typed since");
  assert.equal((saved.recipe as Recipe).filters.q, "");
});

const undoButton = () => [...document.querySelectorAll('[data-testid="toast-viewport"] button')].find((button) => button.textContent === "Deshacer");
async function deleteApplied(page: Page, name: string, left: number) {
  await openMenu(page);
  await page.click(inMenu(`Eliminar ${name}`));
  await page.settle(() => page.fixture.views.length === left);
  await closeMenu(page);
}
async function choose(page: Page, name: string) {
  await openMenu(page);
  await page.click(inMenu(name));
}
async function appliedIs(page: Page, name: string, others: string[]) {
  assert.equal(trigger()!.textContent, name);
  await openMenu(page);
  assert.equal(inMenu(name)!.getAttribute("aria-current"), "true");
  for (const other of others) assert.equal(inMenu(other)!.getAttribute("aria-current"), null, `${other} is not applied`);
  assert.equal(row(name)!.textContent!.includes("Con cambios"), false, "the table shows the applied view's recipe");
  await closeMenu(page);
}

test("Deshacer gives the restored view back its applied place when nothing was chosen since", async () => {
  await mountToasts();
  const page = await mount();
  await saveView(page, "Otra vista");
  await saveView(page, "Mi vista");
  await deleteApplied(page, "Mi vista", 1);
  assert.equal(trigger()!.textContent, "Vistas");
  await page.click(undoButton());
  await page.settle(() => page.fixture.views.length === 2);
  await appliedIs(page, "Mi vista", ["Otra vista"]);
});

test("Deshacer restores the view but keeps a view chosen after the delete", async () => {
  await mountToasts();
  const page = await mount();
  await saveView(page, "Otra vista");
  await search(page, "pena");
  await saveView(page, "Mi vista");
  await deleteApplied(page, "Mi vista", 1);
  await choose(page, "Otra vista");
  await page.click(undoButton());
  await page.settle(() => page.fixture.views.length === 2);
  await appliedIs(page, "Otra vista", ["Mi vista"]);
});

test("a view chosen while Deshacer or a save is still writing stays applied", async () => {
  await mountToasts();
  let release = () => {};
  let held = false;
  const page = await mount({ viewWriteGate: () => held ? new Promise<void>((resolve) => { release = resolve; }) : undefined });
  await saveView(page, "Otra vista");
  await search(page, "pena");
  await saveView(page, "Mi vista");
  await deleteApplied(page, "Mi vista", 1);

  held = true;
  await page.click(undoButton());
  await choose(page, "Otra vista");
  release();
  await page.settle(() => page.fixture.views.length === 2);
  await appliedIs(page, "Otra vista", ["Mi vista"]);

  await search(page, "otra");
  await openMenu(page);
  await page.click(inMenu("Guardar como vista nueva"));
  const field = nameField()!;
  await page.type(field, "Con otra");
  await pressEnter(field);
  await page.click(inMenu("Mi vista"));
  release();
  await page.settle(() => page.fixture.views.length === 3);
  await appliedIs(page, "Mi vista", ["Otra vista", "Con otra"]);
});

async function rename(page: Page, from: string, to: string) {
  await openMenu(page);
  await page.click(inMenu(`Renombrar ${from}`));
  const field = nameField()!;
  await page.type(field, to);
  await pressEnter(field);
}

test("Deshacer pressed while a rename is still writing waits for it, then restores the view", async () => {
  await mountToasts();
  let release = () => {};
  let held = false;
  const page = await mount({ viewWriteGate: () => held ? new Promise<void>((resolve) => { release = resolve; }) : undefined });
  await saveView(page, "Otra vista");
  await search(page, "pena");
  await saveView(page, "Mi vista");
  await deleteApplied(page, "Mi vista", 1);

  held = true;
  await rename(page, "Otra vista", "Renombrada");
  await page.click(undoButton());
  held = false;
  release();
  await page.settle(() => page.fixture.views.length === 2 && page.fixture.views.some((view) => view.name === "Renombrada"));
  assert.deepEqual(page.fixture.views.map((view) => view.name).sort(), ["Mi vista", "Renombrada"]);
  await closeMenu(page);
  await appliedIs(page, "Mi vista", ["Renombrada"]);
});

test("Deshacer applies the restored view itself, not another view that took its name", async () => {
  await mountToasts();
  const page = await mount();
  const other = await saveView(page, "Otra vista");
  await search(page, "pena");
  await saveView(page, "Mi vista");
  await deleteApplied(page, "Mi vista", 1);
  await rename(page, "Otra vista", "Mi vista");
  await page.settle(() => page.fixture.views[0].name === "Mi vista");
  await closeMenu(page);
  await page.click(undoButton());
  await page.settle(() => page.fixture.views.length === 2);
  const restored = page.fixture.views.find((view) => view.id !== other.id)!;
  await openMenu(page);
  const named = [...menu()!.querySelectorAll<HTMLButtonElement>("li button")].filter((button) => button.textContent === "Mi vista");
  assert.equal(named.length, 2, "two views share the name");
  assert.deepEqual(named.map((button) => button.getAttribute("aria-current")), [null, "true"], "the restored view, last in the list, is the applied one");
  assert.equal(menu()!.textContent!.includes("Con cambios"), false, "the table shows the restored view's recipe");
  assert.equal(inMenu("Guardar cambios en «Mi vista»"), undefined, "nothing offers to overwrite the renamed view");
  assert.equal(restored.name, "Mi vista");
});

test("a failed Deshacer says so and keeps Deshacer to try again", async () => {
  await mountToasts();
  let fail = false;
  const page = await mount({ viewWriteGate: () => { if (!fail) return undefined; fail = false; return Promise.reject(new TypeError("connection lost")); } });
  await saveView(page, "Otra vista");
  await search(page, "pena");
  await saveView(page, "Mi vista");
  await deleteApplied(page, "Mi vista", 1);

  fail = true;
  await page.click(undoButton());
  await page.settle(() => Boolean(undoButton()));
  assert.equal(page.fixture.views.length, 1, "nothing was restored");
  assert.match(document.querySelector('[data-testid="toast-viewport"]')!.textContent!, /Se eliminó «Mi vista»/);
  await openMenu(page);
  assert.match(menu()!.textContent!, /No pudimos confirmar si se guardó/, "the menu shows the failed write");
  await closeMenu(page);

  await page.click(undoButton());
  await page.settle(() => page.fixture.views.length === 2);
  assert.equal(viewWrites(page, "POST").filter((call) => (call.body as { name: string }).name === "Mi vista").length, 2, "the save, then one restore");
  await appliedIs(page, "Mi vista", ["Otra vista"]);
});

test("Con cambios shows only while the current recipe differs from the applied view", async () => {
  const page = await mount();
  await saveView(page, "Mi vista");
  await openMenu(page);
  assert.equal(row("Mi vista")!.textContent!.includes("Con cambios"), false);
  assert.ok(inMenu("Guardar vista actual"));
  assert.equal(inMenu("Guardar cambios en «Mi vista»"), undefined);
  assert.equal(inMenu("Guardar como vista nueva"), undefined);
  await closeMenu(page);

  await search(page, "pena");
  await openMenu(page);
  assert.ok(row("Mi vista")!.textContent!.includes("Con cambios"));
  assert.ok(inMenu("Guardar cambios en «Mi vista»"));
  assert.ok(inMenu("Guardar como vista nueva"));
  assert.equal(inMenu("Guardar vista actual"), undefined);
  await closeMenu(page);

  await search(page, "");
  await openMenu(page);
  assert.equal(row("Mi vista")!.textContent!.includes("Con cambios"), false, "back to the saved recipe, no changes");
  assert.ok(inMenu("Guardar vista actual"));
});

test("Guardar cambios updates the applied view with the current recipe", async () => {
  const page = await mount();
  const saved = await saveView(page, "Mi vista");
  const original = structuredClone(saved.recipe) as Recipe;
  await search(page, "pena");
  await openMenu(page);
  await page.click(inMenu("Guardar cambios en «Mi vista»"));
  await page.settle(() => page.fixture.views[0].version === 2);
  const [write] = viewWrites(page, "PATCH");
  assert.deepEqual(write.body, { name: "Mi vista", recipe: { ...original, filters: { ...original.filters, q: "pena" } }, expected_version: 1 });
  await openMenu(page);
  assert.equal(row("Mi vista")!.textContent!.includes("Con cambios"), false);
  assert.ok(inMenu("Guardar vista actual"));
});

test("Guardar como vista nueva keeps the old view and applies the new one", async () => {
  const page = await mount();
  const saved = await saveView(page, "Mi vista");
  await search(page, "pena");
  await openMenu(page);
  await page.click(inMenu("Guardar como vista nueva"));
  assert.ok(row("Mi vista"), "the list stays visible while naming");
  assert.equal(menu()!.textContent!.includes("Guarda los filtros, columnas y orden que ves ahora."), true);
  const field = nameField()!;
  await page.type(field, "Con pena");
  await pressEnter(field);
  await page.settle(() => page.fixture.views.length === 2 && !menu());
  assert.deepEqual(page.fixture.views[0].recipe, saved.recipe);
  assert.equal((page.fixture.views[1].recipe as Recipe).filters.q, "pena");
  assert.equal(trigger()!.textContent, "Con pena");
});

test("an empty menu says how views work", async () => {
  const page = await mount();
  await openMenu(page);
  assert.match(menu()!.textContent!, /Todavía no tienes vistas guardadas\. Ajusta filtros y columnas, y guárdalos para volver con un clic\./);
});
