import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz?view=invoicing" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function mount(width = 1440) {
  (window as unknown as { happyDOM: { setWindowSize: (size: { width: number; height: number }) => void } }).happyDOM.setWindowSize({ width, height: 900 });
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18next = (await import("i18next")).default;
  const english = (await import("@/public/locales/en/common.json")).default;
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { default: InvoicingPreview } = await import("@/components/business-app/invoicing/InvoicingPreview");
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "en", resources: { en: { translation: english } } });
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  const original = crypto.randomUUID();
  const render = async (scope = original, fixture = "") => {
    window.history.replaceState({}, "", `/biz?view=invoicing${fixture ? `&invoicePreview=${fixture}` : ""}`);
    await act(async () => { window.dispatchEvent(new PopStateEvent("popstate")); root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={{ chosen: { space_id: scope, name: "Sample business" }, openPanel: () => undefined } as unknown as BusinessContextValue}><InvoicingPreview /></BusinessContext.Provider></I18nextProvider>); });
  };
  await render();
  const button = (text: string) => {
    const found = [...document.querySelectorAll<HTMLButtonElement>("button")].find(node => (() => { const visible = node.cloneNode(true) as HTMLElement; visible.querySelectorAll('[aria-hidden="true"]').forEach(item => item.remove()); return visible.textContent?.trim() === text; })() && !node.closest("[hidden]"));
    assert.ok(found, `Button not found: ${text}`);
    return found;
  };
  const click = async (text: string) => { await act(async () => button(text).click()); };
  const fill = async (selector: string, value: string) => {
    const input = document.querySelector<HTMLInputElement | HTMLTextAreaElement>(selector)!;
    assert.ok(input, selector);
    await act(async () => { Object.getOwnPropertyDescriptor(input.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, "value")!.set!.call(input, value); input.dispatchEvent(new Event("input", { bubbles: true })); });
  };
  const close = async () => { const control = document.querySelector<HTMLButtonElement>('[data-testid="side-drawer"] button[aria-label="Close"]'); assert.ok(control); await act(async () => control.click()); };
  return { act, click, fill, close, button, render, original, unmount: async () => { await act(async () => root.unmount()); host.remove(); } };
}

test("scheduled drafts reuse the customer and source, survive nested discard, and pause contextually", async () => {
  const page = await mount();
  try {
    await page.render(page.original, "seeded");
    const heads = [...document.querySelectorAll("table thead th")].map(cell => cell.textContent?.trim());
    assert.deepEqual(heads.slice(4, 7), ["Currency", "Total", "Outstanding"]);
    const cells = document.querySelector("table tbody tr")!.querySelectorAll("td");
    assert.equal(cells[4].textContent, "RD$");
    assert.ok(!cells[5].textContent?.includes("RD$"));
    assert.ok(document.querySelector('[class*="phoneList"]')?.textContent?.includes("RD$"));
    await page.click("M-001");
    await page.click("Edit draft");
    await page.click("Next");
    await page.fill('input[id$="-description"]', "Monthly service");
    await page.click("Save draft");
    await page.close();
    await page.click("Scheduled");
    await page.act(async () => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true, bubbles: true })));
    assert.equal(document.activeElement?.getAttribute("aria-label"), "Search schedules");
    await page.click("Create schedule");
    await page.fill("#schedule-name", "Monthly design");
    assert.ok(document.querySelector('[class*="scheduleTemplate"] li .cuadrao-amount'));
    await page.close();
    assert.ok(document.body.textContent?.includes("Discard unsaved schedule changes?"));
    await page.click("Keep editing");
    assert.equal(document.querySelector<HTMLInputElement>('input[type="radio"]')?.checked, true);
    assert.equal(document.querySelector<HTMLInputElement>('input[type="radio"]:disabled')?.disabled, true);
    await page.click("Choose customer");
    await page.click("Add customer");
    await page.fill("#customer-name", "Discard this customer");
    await page.click("Back to schedule");
    await page.click("Discard changes");
    assert.equal(document.querySelector<HTMLInputElement>("#schedule-name")?.value, "Monthly design");
    await page.click("Save schedule");
    assert.ok(!document.querySelector('[data-testid="schedule-dossier"]'));
    await page.click("Pause");
    assert.ok(document.body.textContent?.includes("No active schedules"));
    await page.click("View paused");
    await page.click("Resume");
    await page.click("Active1");
    assert.ok(document.querySelector('[data-testid="schedules-view"]')?.textContent?.includes("Monthly design"));
  } finally { await page.unmount(); }
});

test("Clientes adds, edits, archives and restores without invoices, and scopes sessions by Business and fixture", async () => {
  const page = await mount();
  try {
    await page.click("Customers");
    await page.act(async () => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true, bubbles: true })));
    assert.equal(document.activeElement?.getAttribute("aria-label"), "Search customers");
    await page.click("Add customer");
    await page.click("Save customer");
    assert.equal(document.querySelector("#customer-name")?.getAttribute("aria-invalid"), "true");
    await page.fill("#customer-name", "Brisa test");
    await page.click("Save customer");
    assert.ok(document.querySelector('[data-testid="customer-dossier"]')?.textContent?.includes("No linked invoices yet."));
    await page.click("Edit customer");
    await page.fill("#customer-name", "Brisa updated");
    await page.close();
    assert.ok(document.body.textContent?.includes("Discard changes"));
    await page.click("Save customer");
    assert.ok(!document.querySelector('[data-testid="customer-dossier"]')?.textContent?.includes("Discard changes"));
    await page.click("Archive customer");
    await page.click("Confirm archive");
    await page.close();
    assert.ok(!document.querySelector('[data-testid="customers-view"]')?.textContent?.includes("Brisa updated"));
    await page.click("Archived1");
    await page.click("Brisa updatedNo contact details");
    await page.click("Restore customer");
    await page.close();
    await page.click("Active1");
    assert.ok(document.querySelector('[data-testid="customers-view"]')?.textContent?.includes("Brisa updated"));
    await page.render("another-business");
    await page.click("Customers");
    assert.ok(!document.querySelector('[data-testid="customers-view"]')?.textContent?.includes("Brisa updated"));
    await page.render(page.original, "seeded");
    await page.click("Customers");
    assert.ok(!document.querySelector('[data-testid="customers-view"]')?.textContent?.includes("Brisa updated"));
    await page.render(page.original);
    await page.click("Customers");
    assert.ok(document.querySelector('[data-testid="customers-view"]')?.textContent?.includes("Brisa updated"));
  } finally { await page.unmount(); }
});

test("invoice picker adds a stable customer in the same panel and preserves the draft", async () => {
  const page = await mount();
  try {
    await page.click("Create invoice");
    await page.fill("#invoice-address", "Keep this address");
    await page.click("Choose customer");
    await page.click("Add customer");
    await page.fill("#customer-name", "Discard customer");
    await page.click("Back to draft");
    await page.click("Discard changes");
    assert.equal(document.querySelector<HTMLInputElement>("#invoice-address")?.value, "Keep this address");
    await page.click("Choose customer");
    await page.fill('input[aria-label="Search customers"]', "No matches");
    const enter = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
    await page.act(async () => document.querySelector('input[aria-label="Search customers"]')!.dispatchEvent(enter));
    assert.equal(enter.defaultPrevented, true);
    assert.ok(document.body.textContent?.includes("No customers match this search."));
    await page.click("Add customer");
    assert.equal(document.querySelectorAll('[data-testid="side-drawer"]').length, 1);
    await page.fill("#customer-name", "New customer");
    await page.fill("#customer-email", "new@example.test");
    await page.click("Save customer");
    assert.equal(document.querySelector<HTMLInputElement>("#invoice-name")?.value, "New customer");
    assert.equal(document.querySelector<HTMLInputElement>("#invoice-address")?.value, "");
    await page.click("Choose customer");
    await page.fill('input[aria-label="Search customers"]', "new@example.test");
    await page.click("New customernew@example.test");
    assert.equal(document.querySelector<HTMLInputElement>("#invoice-name")?.value, "New customer");
    await page.close();
    await page.click("Discard changes");
    await page.click("Customers");
    assert.ok(document.querySelector('[data-testid="customers-view"]')?.textContent?.includes("New customer"));
  } finally { await page.unmount(); }
});


test("archived customers leave the new-invoice picker while their saved invoice remains linked", async () => {
  const page = await mount();
  try {
    await page.render(page.original, "seeded");
    await page.click("Customers");
    await page.click("Taller Brisacliente001@example.test");
    assert.ok(document.querySelector('[data-testid="customer-dossier"]')?.textContent?.includes("M-001"));
    await page.click("Archive customer");
    await page.click("Confirm archive");
    await page.close();
    await page.click("Invoices");
    assert.ok(document.querySelector('[data-testid="invoicing-preview"]')?.textContent?.includes("Taller Brisa"));
    await page.click("Create invoice");
    await page.click("Choose customer");
    await page.fill('input[aria-label="Search customers"]', "Taller Brisa");
    assert.ok(document.body.textContent?.includes("No customers match this search."));
  } finally { await page.unmount(); }
});

test("phone customer creation replaces picker content inside one invoice sheet", async () => {
  const page = await mount(389);
  try {
    await page.click("Create invoice");
    await page.fill("#invoice-address", "Phone draft");
    await page.click("Choose customer");
    assert.notEqual(document.activeElement?.getAttribute("aria-label"), "Search customers");
    await page.click("Add customer");
    assert.equal(document.querySelectorAll('[role="dialog"]').length, 1);
    assert.equal(document.querySelector('[data-testid="side-drawer"]'), null);
    await page.fill("#customer-name", "Phone customer");
    await page.click("Save customer");
    assert.equal(document.querySelector<HTMLInputElement>("#invoice-name")?.value, "Phone customer");
    assert.equal(document.querySelector<HTMLInputElement>("#invoice-address")?.value, "");
  } finally { await page.unmount(); }
});

test("invoice steps open expanded, validate the current section and preserve live edits", async () => {
  const page = await mount();
  try {
    await page.render(page.original, "seeded");
    await page.click("M-001");
    await page.click("Edit draft");
    assert.equal(document.querySelector('[data-testid="side-drawer"]')?.getAttribute("data-expanded"), "true");
    assert.equal(document.querySelector('[data-testid="invoice-editor"] h3')?.textContent, "Customer");
    assert.equal(document.querySelector('input[id$="-description"]'), null);
    await page.fill("#invoice-name", "");
    await page.click("Next");
    assert.equal(document.querySelector("#invoice-name")?.getAttribute("aria-invalid"), "true");
    await page.fill("#invoice-name", "Edited customer");
    assert.ok(document.querySelector('[data-testid="invoice-customer-document"] [data-editing="true"]')?.textContent?.includes("Edited customer"));
    await page.click("Next");
    await page.fill('input[id$="-description"]', "Live service");
    assert.ok(document.querySelector('[data-testid="invoice-customer-document"] [data-editing="true"]')?.textContent?.includes("Live service"));
    await page.click("Next");
    assert.ok(document.querySelector("#invoice-issuedOn"));
    await page.fill("textarea", "Pay within 14 days");
    await page.click("Back");
    assert.equal(document.querySelector<HTMLInputElement>('input[id$="-description"]')?.value, "Live service");
    await page.click("Next");
    assert.equal(document.querySelector<HTMLTextAreaElement>("textarea")?.value, "Pay within 14 days");
    await page.click("Next");
    assert.equal(document.querySelector('[data-testid="invoice-editor"] h3')?.textContent, "Review");
    assert.equal(document.querySelector('[data-testid="invoice-customer-document"]')?.getAttribute("data-editing"), "true");
    await page.click("Save draft");
    assert.equal(document.querySelector('[data-testid="invoice-editor"]'), null);
    assert.ok(!document.querySelector('[data-testid="invoice-customer-document"] [data-editing]'));
  } finally { await page.unmount(); }
});

test("phone keeps step data through preview and full-save validation routes to missing items", async () => {
  const page = await mount(390);
  try {
    await page.render(page.original, "seeded");
    await page.click("Create invoice");
    await page.click("Choose customer");
    await page.click("Taller Brisacliente001@example.test");
    await page.click("Save draft");
    assert.equal(document.querySelector('[data-testid="invoice-editor"] h3')?.textContent, "Items");
    assert.equal(document.querySelector('input[id$="-description"]')?.getAttribute("aria-invalid"), "true");
    assert.equal(document.activeElement, document.querySelector('input[id$="-description"]'));
    await page.fill('input[id$="-description"]', "Phone service");
    await page.click("Preview");
    assert.equal(document.querySelector('[data-testid="invoice-editor"]')?.getAttribute("data-view"), "preview");
    assert.ok(document.querySelector('[data-testid="invoice-customer-document"]')?.textContent?.includes("Phone service"));
    await page.click("Edit");
    assert.equal(document.querySelector<HTMLInputElement>('input[id$="-description"]')?.value, "Phone service");
    assert.equal(document.querySelector('[data-testid="side-drawer"]'), null);
  } finally { await page.unmount(); }
});
