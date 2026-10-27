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
    const found = [...document.querySelectorAll<HTMLButtonElement>("button")].find(node => (() => { const visible = node.cloneNode(true) as HTMLElement; visible.querySelectorAll('[aria-hidden="true"]').forEach(item => item.remove()); return (visible.textContent?.trim() === text || text === "Choose customer" && node.getAttribute("aria-label") === text); })() && !node.closest("[hidden]"));
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

test("invoice customer field starts quiet, creates inline once and preserves the saved profile", async () => {
  const page = await mount();
  try {
    await page.click("Create invoice");
    assert.equal(document.querySelector("#invoice-name"), null);
    assert.equal(document.querySelectorAll('label[for="invoice-customer-search"]').length, 1);
    assert.equal(document.querySelector("#invoice-email"), null);
    assert.ok(document.querySelector('[role="combobox"]')?.getAttribute("aria-describedby"));
    await page.fill("#invoice-customer-search", "New customer");
    assert.ok(document.body.textContent?.includes("No customers match this search."));
    const enter = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
    await page.act(async () => document.querySelector("#invoice-customer-search")!.dispatchEvent(enter));
    assert.equal(enter.defaultPrevented, true);
    assert.equal(document.querySelectorAll('[data-testid="side-drawer"]').length, 1);
    assert.ok(document.querySelector('[data-testid="invoice-customer-document"]'));
    assert.equal(document.querySelector<HTMLInputElement>("#invoice-customer-search")?.value, "New customer");
    assert.equal(document.querySelector("#invoice-name"), null);
    assert.equal(document.querySelector('[role="combobox"]')?.getAttribute("aria-describedby"), null);
    await page.fill("#invoice-customer-search", "New customer edited");
    assert.equal(document.querySelector('[role="listbox"]'), null);
    assert.ok(document.querySelector('[data-testid="invoice-customer-document"]')?.textContent?.includes("New customer edited"));
    await page.fill("#invoice-email", "invalid");
    await page.click("Next");
    assert.equal(document.querySelector("#invoice-email")?.getAttribute("aria-invalid"), "true");
    await page.fill("#invoice-email", "new@example.test");
    await page.click("Next");
    await page.click("Back");
    await page.fill("#invoice-customer-search", "Invoice-only name");
    await page.click("Next");
    await page.close();
    await page.click("Discard changes");
    await page.click("Customers");
    const rows = document.querySelectorAll('[data-testid="customers-view"] table tbody tr');
    assert.equal(rows.length, 1);
    assert.ok(rows[0].textContent?.includes("New customer edited"));
    assert.ok(!rows[0].textContent?.includes("Invoice-only name"));
  } finally { await page.unmount(); }
});

test("customer field searches saved customers with arrows, Enter and Escape", async () => {
  const page = await mount();
  try {
    await page.render(page.original, "seeded");
    await page.click("Create invoice");
    await page.fill("#invoice-customer-search", "cliente001@example.test");
    const input = document.querySelector<HTMLInputElement>("#invoice-customer-search")!;
    await page.act(async () => input.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true, cancelable: true })));
    assert.ok(input.getAttribute("aria-activedescendant")?.endsWith("-1"));
    await page.act(async () => input.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowUp", bubbles: true, cancelable: true })));
    await page.act(async () => input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true })));
    assert.equal(document.querySelector<HTMLInputElement>("#invoice-customer-search")?.value, "Taller Brisa");
    assert.equal(document.querySelector("#invoice-name"), null);
    assert.equal(input.getAttribute("aria-describedby"), null);
    assert.equal(document.querySelector<HTMLInputElement>("#invoice-email")?.value, "cliente001@example.test");
    await page.click("Choose customer");
    await page.act(async () => input.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true })));
    assert.equal(document.querySelector('[role="listbox"]'), null);
    assert.ok(document.querySelector('[data-testid="invoice-editor"]'));
    assert.equal(input.value, "Taller Brisa");
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
    await page.fill("#invoice-customer-search", "Taller Brisa");
    assert.ok(document.body.textContent?.includes("No customers match this search."));
  } finally { await page.unmount(); }
});

test("phone creates the customer inline within the invoice sheet", async () => {
  const page = await mount(389);
  try {
    await page.click("Create invoice");
    assert.notEqual(document.activeElement?.id, "invoice-customer-search");
    await page.click("Choose customer");
    await page.click("Add customer");
    assert.equal(document.querySelectorAll('[role="dialog"]').length, 1);
    assert.equal(document.querySelector('[data-testid="side-drawer"]'), null);
    await page.fill("#invoice-customer-search", "Phone customer");
    await page.fill("#invoice-address", "Phone draft");
    await page.click("Next");
    await page.click("Back");
    assert.equal(document.querySelector<HTMLInputElement>("#invoice-customer-search")?.value, "Phone customer");
    assert.equal(document.querySelector<HTMLInputElement>("#invoice-address")?.value, "Phone draft");
  } finally { await page.unmount(); }
});


test("invoice steps open expanded, validate the current section and preserve live edits", async () => {
  const page = await mount();
  try {
    await page.render(page.original, "seeded");
    await page.click("M-001");
    await page.click("Edit draft");
    assert.equal(document.querySelector('[data-testid="side-drawer"]')?.getAttribute("data-expanded"), "true");
    assert.equal(document.querySelector('[data-testid="invoice-editor"] h3')?.textContent, "Who is this invoice for?");
    assert.equal(document.querySelector('input[id$="-description"]'), null);
    await page.fill("#invoice-customer-search", "");
    await page.click("Next");
    assert.equal(document.querySelector("#invoice-customer-search")?.getAttribute("aria-invalid"), "true");
    assert.equal(document.activeElement?.id, "invoice-customer-search");
    const errorId = document.activeElement?.getAttribute("aria-describedby");
    assert.ok(errorId && document.getElementById(errorId));
    await page.fill("#invoice-customer-search", "Edited customer");
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
    assert.equal(document.querySelector('[data-testid="invoice-editor"] h3')?.textContent, "Your invoice is ready");
    assert.equal(document.querySelector('[data-testid="invoice-customer-document"]')?.getAttribute("data-editing"), "true");
    await page.click("Save draft");
    assert.equal(document.querySelector('[data-testid="invoice-editor"]'), null);
    assert.ok(!document.querySelector('[data-testid="invoice-customer-document"] [data-editing]'));
  } finally { await page.unmount(); }
});

test("phone saves incomplete drafts and keeps step data through preview", async () => {
  const page = await mount(390);
  try {
    await page.render(page.original, "seeded");
    await page.click("Create invoice");
    await page.click("Choose customer");
    await page.click("Taller Brisacliente001@example.test");
    await page.click("Save draft");
    assert.equal(document.querySelector('[data-testid="invoice-editor"]'), null);
    assert.equal(page.button("Issue in sample").disabled, true);
    await page.click("Edit draft");
    await page.click("Next");
    await page.click("Next");
    assert.equal(document.querySelector('[data-testid="invoice-editor"] h3')?.textContent, "Details");
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


test("invoice review keeps item discounts and email preparation in the same draft", async () => {
  const page = await mount();
  try {
    await page.render(page.original, "seeded");
    await page.click("M-001");
    await page.click("Edit draft");
    await page.click("Next");
    await page.fill('input[id$="-description"]', "Design service");
    await page.fill('input[id$="-discount"]', "10");
    await page.fill('textarea', "Invoice note");
    await page.click("Next");
    await page.click("Next");
    await page.fill("#invoice-email-to", "bad-address");
    await page.act(async () => document.querySelector<HTMLInputElement>("#invoice-email-to")!.dispatchEvent(new FocusEvent("focusout", { bubbles: true })));
    assert.equal(document.querySelector("#invoice-email-to")?.getAttribute("aria-invalid"), "true");
    await page.fill("#invoice-email-message", "A separate message");
    await page.click("Save preparation");
    assert.equal(document.querySelector("#invoice-email-to")?.getAttribute("aria-invalid"), "true");
    const preview = document.querySelector('[data-testid="invoice-email-preview"]');
    assert.ok(preview?.textContent?.includes("A separate message"));
    assert.ok(!preview?.textContent?.includes("Invoice note"));
    await page.click("Save draft");
    await page.click("Edit draft");
    await page.click("Next");
    assert.equal(document.querySelector<HTMLInputElement>('input[id$="-discount"]')?.value, "10");
    await page.click("Next");
    await page.click("Next");
    assert.equal(document.querySelector<HTMLInputElement>("#invoice-email-to")?.value, "bad-address");
    await page.fill("#invoice-email-to", "customer@example.test");
    await page.fill("#invoice-email-cc", "accounts@example.test");
    await page.click("Save preparation");
    assert.ok(!document.querySelector('[data-testid="invoice-editor"]'));
    assert.ok(document.body.textContent?.includes("Draft"));
    assert.ok(!document.body.textContent?.includes("Email sent"));
  } finally { await page.unmount(); }
});


test("saved invoice customer fields validate without truncation and preview keeps contact order", async () => {
  const page = await mount();
  try {
    await page.render(page.original, "seeded");
    await page.click("M-001");
    await page.click("Edit draft");
    const section = document.querySelector('[data-testid="invoice-customer-document"] [data-editing="true"]')!;
    const invalidTaxId = "18273456542732632632535232323";
    await page.fill("#invoice-taxId", invalidTaxId);
    await page.act(async () => document.querySelector("#invoice-taxId")!.dispatchEvent(new FocusEvent("focusout", { bubbles: true })));
    assert.equal(document.querySelector("#invoice-taxId")?.getAttribute("aria-invalid"), "true");
    assert.equal(document.querySelector<HTMLInputElement>("#invoice-taxId")?.value, invalidTaxId);
    assert.ok(section.textContent?.includes(invalidTaxId));
    await page.fill("#invoice-taxId", "123456789");
    await page.act(async () => document.querySelector("#invoice-taxId")!.dispatchEvent(new FocusEvent("focusout", { bubbles: true })));
    assert.equal(document.querySelector<HTMLInputElement>("#invoice-taxId")?.value, "1-23-45678-9");
    assert.notEqual(document.querySelector("#invoice-taxId")?.getAttribute("aria-invalid"), "true");
    await page.fill("#invoice-email", "not-an-email");
    await page.click("Next");
    assert.equal(document.querySelector("#invoice-email")?.getAttribute("aria-invalid"), "true");
    await page.fill("#invoice-email", "customer@example.test");
    await page.fill("#invoice-address", "Calle de muestra 4");
    assert.equal(document.querySelector('[data-testid="invoice-customer-document"] [data-editing="true"]'), section);
    assert.deepEqual([...section.children].map(node => node.textContent), ["Bill to", "Taller Brisa", "RNC: 1-23-45678-9", "customer@example.test", "Calle de muestra 4"]);
    await page.fill("#invoice-address", "");
    assert.ok([...section.children].every(node => node.textContent?.trim()));
    await page.click("Next");
    assert.equal(document.querySelector('[data-testid="invoice-editor"] h3')?.textContent, "Details");
  } finally { await page.unmount(); }
});


test("document type belongs to terms and fiscal credit routes back to missing customer tax ID", async () => {
  const page = await mount();
  try {
    await page.render(page.original, "seeded");
    await page.click("M-001");
    await page.click("Edit draft");
    assert.equal(document.querySelector('button[aria-label^="Document type:"]'), null);
    await page.click("Next");
    await page.fill('input[id$="-description"]', "Service");
    await page.click("Next");
    assert.ok(document.querySelector('button[aria-label^="Document type:"]'));
    assert.ok(document.querySelector('[data-testid="invoice-editor"] form')?.textContent?.includes("Document type"));
    await page.click("E32 · Consumer invoice");
    await page.click("E31 · Fiscal credit");
    await page.click("Next");
    assert.equal(document.querySelector('[data-testid="invoice-editor"] h3')?.textContent, "Who is this invoice for?");
    assert.equal(document.querySelector("#invoice-taxId")?.getAttribute("aria-invalid"), "true");
    assert.equal(document.activeElement?.id, "invoice-taxId");
    assert.equal(document.querySelector('button[aria-label^="Document type:"]'), null);
    await page.fill("#invoice-taxId", "123456789");
    await page.click("Next");
    await page.click("Next");
    assert.ok(document.querySelector('button[aria-label="Document type: E31 · Fiscal credit"]'));
    await page.click("Next");
    assert.equal(document.querySelector('[data-testid="invoice-editor"] h3')?.textContent, "Your invoice is ready");
  } finally { await page.unmount(); }
});

test("item editor checks before adding, collapses earlier items and reopens invalid items", async () => {
  const page = await mount();
  try {
    await page.render(page.original, "seeded");
    await page.click("M-001"); await page.click("Edit draft"); await page.click("Next");
    await page.fill('input[id$="-description"]', "");
    await page.click("Add product");
    assert.equal(document.querySelectorAll('fieldset[id^="invoice-item-"]').length, 1);
    assert.equal(document.activeElement, document.querySelector('input[id$="-description"]'));
    await page.fill('input[id$="-description"]', "First service");
    await page.click("Add product");
    assert.equal(document.querySelectorAll('fieldset[id^="invoice-item-"]').length, 2);
    assert.equal(document.querySelectorAll('input[id$="-description"]').length, 1);
    assert.equal(document.activeElement, document.querySelector('input[id$="-description"]'));
    await page.act(async () => document.querySelector<HTMLButtonElement>('button[aria-label="Edit item 1: First service"]')!.click());
    assert.equal(document.querySelector<HTMLInputElement>('input[id$="-description"]')?.value, "First service");
    await page.click("Next");
    assert.equal(document.querySelector<HTMLInputElement>('input[id$="-description"]')?.value, "");
    assert.equal(document.activeElement, document.querySelector('input[id$="-description"]'));
    await page.fill('input[id$="-description"]', "Second service");
    await page.fill('input[id$="-price"]', "25");
    assert.ok(document.querySelector('[data-testid="invoice-customer-document"]')?.textContent?.includes("Second service"));
    await page.act(async () => document.querySelector<HTMLButtonElement>('button[aria-label="Remove item 2"]')!.click());
    assert.equal(document.querySelectorAll('fieldset[id^="invoice-item-"]').length, 1);
    assert.equal(document.querySelector<HTMLInputElement>('input[id$="-description"]')?.value, "First service");
    assert.equal(document.activeElement, document.querySelector('input[id$="-description"]'));
  } finally { await page.unmount(); }
});

test("item amounts preserve invalid pasted values and format valid decimals on blur", async () => {
  const page = await mount();
  try {
    await page.render(page.original, "seeded");
    await page.click("M-001"); await page.click("Edit draft"); await page.click("Next");
    await page.fill('input[id$="-description"]', "Service");
    const blur = async (key: string) => page.act(async () => document.querySelector<HTMLInputElement>(`input[id$="-${key}"]`)!.dispatchEvent(new FocusEvent("focusout", { bubbles: true })));
    for (const invalid of ["1e3", "-12", "Infinity", "12.345", "10000000"]) {
      await page.fill('input[id$="-price"]', invalid); await blur("price");
      assert.equal(document.querySelector('input[id$="-price"]')?.getAttribute("aria-invalid"), "true", invalid);
      await page.click("Add product");
      assert.equal(document.querySelectorAll('fieldset[id^="invoice-item-"]').length, 1);
    }
    const price = document.querySelector<HTMLInputElement>('input[id$="-price"]')!;
    await page.act(async () => {
      price.setSelectionRange(0, price.value.length);
      const data = new DataTransfer(); data.setData("text", "123456789012.34");
      price.dispatchEvent(new ClipboardEvent("paste", { bubbles: true, cancelable: true, clipboardData: data }));
    });
    assert.equal(price.value, "123456789012.34");
    assert.equal(price.getAttribute("aria-invalid"), "true");
    await page.fill('input[id$="-price"]', "12,5"); await blur("price");
    assert.equal(price.value, "12.50");
    assert.notEqual(price.getAttribute("aria-invalid"), "true");
    await page.fill('input[id$="-quantity"]', "1000.01"); await blur("quantity");
    assert.equal(document.querySelector('input[id$="-quantity"]')?.getAttribute("aria-invalid"), "true");
    await page.fill('input[id$="-quantity"]', "1000");
    await page.fill('input[id$="-tax"]', "100.01"); await blur("tax");
    assert.equal(document.querySelector('input[id$="-tax"]')?.getAttribute("aria-invalid"), "true");
    await page.fill('input[id$="-tax"]', "100");
    await page.fill('input[id$="-discount"]', "12500.01"); await blur("discount");
    assert.equal(document.querySelector('input[id$="-discount"]')?.getAttribute("aria-invalid"), "true");
    await page.fill('input[id$="-discount"]', "0"); await page.click("Next");
    assert.ok(document.querySelector("#invoice-issuedOn"));
  } finally { await page.unmount(); }
});
