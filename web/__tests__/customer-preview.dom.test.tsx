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
    await page.fill('textarea', "Keep these terms");
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
    assert.equal(document.querySelector<HTMLTextAreaElement>("textarea")?.value, "Keep these terms");
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
    await page.fill('textarea', "Phone draft");
    await page.click("Choose customer");
    assert.notEqual(document.activeElement?.getAttribute("aria-label"), "Search customers");
    await page.click("Add customer");
    assert.equal(document.querySelectorAll('[role="dialog"]').length, 1);
    assert.equal(document.querySelector('[data-testid="side-drawer"]'), null);
    await page.fill("#customer-name", "Phone customer");
    await page.click("Save customer");
    assert.equal(document.querySelector<HTMLInputElement>("#invoice-name")?.value, "Phone customer");
    assert.equal(document.querySelector<HTMLTextAreaElement>("textarea")?.value, "Phone draft");
  } finally { await page.unmount(); }
});
