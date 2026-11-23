import assert from "node:assert/strict";
import { describe, test } from "bun:test";
import { button, fill, kindAsked, openList, pick, registerReceiptReviewPage, setup } from "./fixtures/receipt-review-page";

registerReceiptReviewPage();

const footer = (page: { host: ParentNode }) => page.host.querySelector<HTMLElement>('[data-testid="receipt-review-footer"]')!;
/** What the row holds: label, status, value, action. The line under a row counts only when it says something; empty, CSS hides it. */
const slots = (row: HTMLElement) => [...row.children].filter((child) => child.childNodes.length > 0 || child.tagName !== "DIV").map((child) => child.tagName);

describe("the footer of a read record", () => {
  test("Más stands first, outside the actions, and the accept buttons are the actions", async () => {
    const page = await setup();
    try {
      const controls = [...footer(page).querySelectorAll<HTMLButtonElement>("button")].filter((item) => !item.closest('[role="menu"]'));
      assert.equal(controls[0].textContent, "Más");
      const actions = footer(page).querySelector<HTMLElement>("[data-footer-actions]")!;
      assert.equal(actions.contains(controls[0]), false, "Más is not one of the right-hand actions");
      assert.deepEqual([...actions.querySelectorAll("button")].map((item) => item.textContent), ["Aceptar"]);
      assert.ok(actions.compareDocumentPosition(controls[0]) & Node.DOCUMENT_POSITION_PRECEDING, "Más comes before the actions");
    } finally { await page.close(); }
  });

  test("what holds approval is said between Más and the actions, never above the form", async () => {
    const page = await setup();
    try {
      await page.openRow("counterparty");
      await fill(page, '[data-testid="edit-counterparty"] input', "Ferretería Norte");
      const reason = footer(page).querySelector('[data-testid="approve-reason"]')!;
      assert.equal(reason.textContent, "Guarda o cancela Emisor para aceptar.");
      const more = footer(page).querySelector('[data-testid="receipt-more"]')!;
      const actions = footer(page).querySelector("[data-footer-actions]")!;
      assert.ok(more.compareDocumentPosition(reason) & Node.DOCUMENT_POSITION_FOLLOWING);
      assert.ok(actions.compareDocumentPosition(reason) & Node.DOCUMENT_POSITION_PRECEDING);
    } finally { await page.close(); }
  });
});

describe("Compra or Venta on the General tab", () => {
  test("a clean purchase has no Tipo row", async () => {
    const page = await setup();
    try {
      assert.equal(page.host.querySelector('[data-fact="document_type"]'), null);
      assert.equal(page.host.querySelector('[data-fact="kind"]'), null);
    } finally { await page.close(); }
  });

  test("a purchase whose kind the server waits on shows Tipo, with its edit", async () => {
    const page = await setup("fiscal", kindAsked);
    try {
      assert.match(page.row("document_type").textContent ?? "", /Tipo\s*Compra/);
      assert.ok(page.row("document_type").querySelector('button[aria-label="Editar detalles · Tipo"]'));
      assert.ok(page.row("kind"), "the kind row waits beside it");
    } finally { await page.close(); }
  });

  test("a clean sale has no Tipo row either: the Venta switch of Más says it", async () => {
    const page = await setup("fiscal", (dossier) => { dossier.document_type = "venta"; });
    try {
      assert.equal(page.host.querySelector('[data-fact="document_type"]'), null);
      assert.equal(page.host.querySelector('[data-testid="receipt-mark-sale"]')?.getAttribute("aria-checked"), "true");
    } finally { await page.close(); }
  });
});

describe("a row edited in place", () => {
  test("the field opens in the value slot, the check and the X in the action slot, and nothing is added under the row", async () => {
    const page = await setup();
    try {
      const row = page.row("counterparty");
      const closed = slots(row);
      assert.deepEqual(closed, ["SPAN", "SPAN", "BUTTON", "SPAN"]);
      await page.openRow("counterparty");
      assert.deepEqual(slots(row), ["SPAN", "SPAN", "DIV", "SPAN"]);
      assert.ok(row.children[2].querySelector("input"), "the field sits where the value was");
      assert.deepEqual([...row.children[3].querySelectorAll("button")].map((item) => item.getAttribute("aria-label")), ["Guardar · Emisor", "Cancelar · Emisor"]);
    } finally { await page.close(); }
  });

  test("Guardado shows once in the action slot, adds no line, and leaves by itself", async () => {
    const page = await setup();
    try {
      const row = page.row("counterparty");
      await page.openRow("counterparty");
      await fill(page, '[data-testid="edit-counterparty"] input', "Ferretería Norte");
      await page.check("counterparty");
      await page.wait(() => Boolean(row.querySelector('[data-testid="row-saved"]')));
      const saved = row.querySelector<HTMLElement>('[data-testid="row-saved"]')!;
      assert.equal(saved.textContent, "Guardado");
      assert.equal(saved.getAttribute("role"), "status");
      assert.equal(saved.parentElement, row.children[3], "in the action slot");
      assert.deepEqual(slots(row), ["SPAN", "SPAN", "BUTTON", "SPAN"], "no line under the row");
      await page.act(async () => { await new Promise((resolve) => setTimeout(resolve, 2500)); });
      assert.equal(row.querySelector('[data-testid="row-saved"]'), null, "it leaves without a press");
      assert.ok(row.children[3].querySelector('button[aria-label="Editar detalles · Emisor"]'), "the pencil is back");
    } finally { await page.close(); }
  });

  test("a saved pick says Guardado where its chevron is", async () => {
    const page = await setup();
    try {
      const trigger = () => page.row("category").querySelector<HTMLElement>('button[aria-haspopup="listbox"]')!;
      assert.ok(trigger().querySelector("svg.lucide-chevron-down"), "the chevron marks a row that opens a list");
      await pick(page, "category", "05");
      await page.wait(() => Boolean(trigger().querySelector('[data-testid="row-saved"]')));
      assert.equal(page.row("category").querySelector("[data-row-value]")?.textContent, "Gastos de representación");
      assert.deepEqual(slots(page.row("category")), ["SPAN", "SPAN", "BUTTON"], "label, status, and the value with its action as one control");
    } finally { await page.close(); }
  });
});

describe("a choice row's list", () => {
  test("arrows walk the options, Escape closes it without a write and hands focus back to the row", async () => {
    const page = await setup();
    try {
      const options = await openList(page, "payment_method");
      const key = (name: string) => page.act(async () => { document.activeElement!.dispatchEvent(new KeyboardEvent("keydown", { key: name, bubbles: true, cancelable: true })); });
      assert.equal(document.activeElement, options[2], "the list opens on the value shown");
      await key("ArrowDown");
      assert.equal(document.activeElement, options[3]);
      await key("Home");
      assert.equal(document.activeElement, options[0]);
      await key("Escape");
      assert.equal(page.row("payment_method").querySelector('[role="listbox"]'), null);
      assert.equal(document.activeElement, page.row("payment_method").querySelector('button[aria-haspopup="listbox"]'));
      assert.equal(page.writes.length, 0);
      assert.ok(button(page.host, "Aceptar"), "the dossier stays open");
    } finally { await page.close(); }
  });

  test("a press outside closes the list", async () => {
    const page = await setup();
    try {
      await openList(page, "category");
      await page.act(async () => { page.row("counterparty").dispatchEvent(new Event("pointerdown", { bubbles: true })); });
      assert.equal(page.row("category").querySelector('[role="listbox"]'), null);
    } finally { await page.close(); }
  });

  test("a record whose 606 answers the server closes shows them as text, with no list", async () => {
    const page = await setup("fiscal", (dossier) => { dossier.declaration_editable = false; dossier.dgii = { form: "606", category: "02", payment_method: "01" }; });
    try {
      for (const choice of ["category", "payment_method"]) assert.equal(page.row(choice).querySelector("button, select"), null, choice);
      assert.match(page.row("category").textContent ?? "", /Gastos por trabajos/);
    } finally { await page.close(); }
  });
});
