import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function mount(expandable: boolean, width = 1440) {
  (window as unknown as { happyDOM: { setWindowSize: (size: { width: number; height: number }) => void } }).happyDOM.setWindowSize({ width, height: 900 });
  const { act, useState } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { default: AdaptivePanel } = await import("@/components/ui/AdaptivePanel");
  const { I18nextProvider } = await import("react-i18next");
  const i18next = (await import("i18next")).default;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "en", resources: { en: { translation: { common: { back: "Back" } } } } });
  let closed = 0;
  function Example() {
    const [expanded, setExpanded] = useState(false);
    return <I18nextProvider i18n={i18n}><AdaptivePanel title="Invoice" closeLabel="Close" width="lg" snaps={["full"]} initialSnap="full" onClose={() => { closed++; }} expansion={expandable ? { expanded, onToggle: () => setExpanded(value => !value), expandLabel: "Expand", collapseLabel: "Collapse" } : undefined}><input aria-label="Draft" defaultValue="Preserve this draft" /></AdaptivePanel></I18nextProvider>;
  }
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => { root.render(<Example />); });
  return { act, closeCount: () => closed, unmount: async () => { await act(async () => root.unmount()); host.remove(); } };
}

test("existing AdaptivePanel consumers keep their width, close control and no expansion action", async () => {
  const page = await mount(false);
  const panel = document.querySelector<HTMLElement>('[data-testid="side-drawer"]')!;
  assert.equal(panel.style.minWidth, "320px");
  assert.equal(document.documentElement.style.getPropertyValue("--cuadrao-drawer-space"), "560px");
  assert.equal(panel.getAttribute("role"), "dialog");
  assert.equal(panel.querySelector('[aria-label="Expand"]'), null);
  await page.act(async () => { (panel.querySelector('[aria-label="Close"]') as HTMLButtonElement).click(); });
  assert.equal(page.closeCount(), 1);
  await page.unmount();
  assert.equal(document.documentElement.style.getPropertyValue("--cuadrao-drawer-space"), "");
});

test("opt-in expansion preserves draft DOM, focus and the workspace's normal width claim", async () => {
  const page = await mount(true);
  const input = document.querySelector<HTMLInputElement>('input[aria-label="Draft"]')!;
  input.value = "Unsaved changes";
  const control = document.querySelector<HTMLButtonElement>('[aria-label="Expand"]')!;
  control.focus();
  const claim = document.documentElement.style.getPropertyValue("--cuadrao-drawer-space");
  await page.act(async () => control.click());
  assert.equal(document.querySelector<HTMLElement>('[data-testid="side-drawer"]')!.style.minWidth, "720px");
  assert.equal(document.querySelector('[data-testid="side-drawer"]')!.getAttribute("data-expanded"), "true");
  assert.equal(document.querySelector('input[aria-label="Draft"]'), input);
  assert.equal(input.value, "Unsaved changes");
  assert.equal(document.activeElement, control);
  assert.equal(document.documentElement.style.getPropertyValue("--cuadrao-drawer-space"), claim);
  await page.act(async () => control.click());
  assert.equal(document.querySelector('input[aria-label="Draft"]'), input);
  assert.equal(input.value, "Unsaved changes");
  await page.unmount();
});

test("phone remains one full sheet and never gets a desktop expansion control", async () => {
  const page = await mount(true, 390);
  assert.equal(document.querySelector('[data-testid="side-drawer"]'), null);
  assert.equal(document.querySelector('[aria-label="Expand"]'), null);
  assert.ok(document.querySelector('input[aria-label="Draft"]'));
  assert.equal(document.documentElement.style.getPropertyValue("--cuadrao-drawer-space"), "");
  await page.unmount();
});

test("invoice stage tabs announce real counts and support arrow, Home and End keys", async () => {
  const { act, useState } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18next = (await import("i18next")).default;
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { default: InvoiceStageTabs } = await import("@/components/business-app/invoicing/InvoiceStageTabs");
  const { invoicePreviewSeed } = await import("@/components/business-app/invoicing/invoice-preview-model");
  type InvoiceFilter = import("@/components/business-app/invoicing/invoice-preview-model").InvoiceFilter;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  function Example() {
    const [value, setValue] = useState<InvoiceFilter>("all");
    return <I18nextProvider i18n={i18n}><InvoiceStageTabs value={value} invoices={invoicePreviewSeed("correction-confirmed", "Motivo")} onChange={setValue} /><div id="invoice-stage-results" role="tabpanel" aria-labelledby={`invoice-stage-${value}`} /></I18nextProvider>;
  }
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  await act(async () => root.render(<Example />));
  const tabs = [...host.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
  assert.deepEqual(tabs.map(tab => tab.textContent), ["Todas4", "Borradores1", "Por cobrar1", "Cobradas0", "Anuladas1"]);
  assert.equal(tabs.filter(tab => tab.tabIndex === 0).length, 1);
  await act(async () => tabs[0].dispatchEvent(new KeyboardEvent("keydown", { key: "End", bubbles: true })));
  assert.equal(document.activeElement, tabs[4]);
  assert.equal(tabs[4].getAttribute("aria-selected"), "true");
  assert.equal(host.querySelector('[role="tabpanel"]')!.getAttribute("aria-labelledby"), tabs[4].id);
  await act(async () => tabs[4].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true })));
  assert.equal(document.activeElement, tabs[0]);
  await act(async () => tabs[0].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true })));
  assert.equal(document.activeElement, tabs[4]);
  await act(async () => tabs[4].dispatchEvent(new KeyboardEvent("keydown", { key: "Home", bubbles: true })));
  assert.equal(document.activeElement, tabs[0]);
  await act(async () => root.unmount()); host.remove();
});

test("invoice calendar errors label the input and clear after repair", async () => {
  const { act, useState } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { default: InvoiceDateField } = await import("@/components/business-app/invoicing/InvoiceDateField");
  const { I18nextProvider } = await import("react-i18next");
  const i18next = (await import("i18next")).default;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: {} } } });
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  function InvalidDate() {
    const [value, setValue] = useState("2026-10-26");
    return <InvoiceDateField id="due-date" label="Vencimiento" value={value} error="Revisa la fecha" onChange={setValue} onBlur={() => undefined} />;
  }
  await act(async () => root.render(<I18nextProvider i18n={i18n}><InvalidDate /></I18nextProvider>));
  const input = host.querySelector("input")!;
  assert.equal(input.getAttribute("aria-invalid"), "true");
  assert.equal(input.getAttribute("aria-describedby"), "due-date-error");
  assert.equal(host.querySelector("#due-date-error")!.textContent, "Revisa la fecha");
  for (const value of ["not a date", ""]) {
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    assert.equal(input.getAttribute("aria-invalid"), "true", "required date stays invalid when invalid text is cleared");
    assert.equal(input.getAttribute("aria-describedby"), "due-date-error");
  }
  await act(async () => root.render(<I18nextProvider i18n={i18n}><InvoiceDateField id="due-date" label="Vencimiento" value="2026-10-27" error={null} onChange={() => undefined} onBlur={() => undefined} /></I18nextProvider>));
  const repaired = host.querySelector("input")!;
  assert.equal(repaired.getAttribute("aria-invalid"), "false");
  assert.equal(repaired.getAttribute("aria-describedby"), null);
  await act(async () => root.unmount()); host.remove();
});
