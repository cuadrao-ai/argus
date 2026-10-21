import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import type { Period, PeriodKey } from "@/components/business-app/business-format";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1280, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function mount(width: number, period: Period = { key: "this_month", from: "2026-10-01", to: "2026-10-31" } as Period) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 900 });
  const { default: BusinessPeriodControl } = await import("@/components/business-app/BusinessPeriodControl");
  const picked: (PeriodKey | Period)[] = [];
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessPeriodControl period={period} setPeriod={(next) => picked.push(next)} /></I18nextProvider>));
  return { host, picked, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

test("on a phone the period is one native picker that fits any width, never a bar that runs off the screen", async () => {
  const page = await mount(390);
  try {
    assert.equal(page.host.querySelector('[role="radiogroup"], [data-testid="segmented-control"]'), null, "no segmented bar on a phone");
    const select = page.host.querySelector<HTMLSelectElement>("select");
    assert.ok(select, "a native picker");
    assert.deepEqual([...select.options].map((option) => option.value), ["this_month", "last_month", "last_30_days", "all", "custom"]);
    assert.equal(select.value, "this_month");
    assert.ok(select.getAttribute("aria-label"));
    await act(async () => { select.value = "last_30_days"; select.dispatchEvent(new Event("change", { bubbles: true })); });
    assert.deepEqual(page.picked, ["last_30_days"]);
  } finally { await page.close(); }
});

test("on a desktop the period stays a segmented bar", async () => {
  const page = await mount(1280);
  try {
    assert.equal(page.host.querySelector("select"), null);
  } finally { await page.close(); }
});

const day = (iso: string) => document.querySelector<HTMLButtonElement>(`[data-testid="range-calendar"] button[data-day="${iso}"]`)!;
const click = (node: Element | null) => act(async () => { (node as HTMLElement).click(); });

test("Personalizado opens the range calendar in a popover under its segment; nothing in the row moves and no browser date field shows", async () => {
  const page = await mount(1280);
  try {
    const row = page.host.querySelector('[data-testid="business-period-control"]')!;
    const before = row.children.length;
    await click(page.host.querySelector('[data-segment="custom"]'));
    const popover = page.host.querySelector('[data-testid="period-popover"]')!;
    assert.ok(popover, "a popover");
    assert.equal(popover.getAttribute("role"), "dialog");
    assert.match(popover.className, /absolute/, "it floats over the page instead of pushing the row");
    assert.ok(popover.querySelector('[data-testid="range-calendar"]'), "the export's range calendar");
    assert.equal(document.querySelector('input[type="date"]'), null);
    assert.equal(row.children.length, before + 1, "only the floating popover joins the row");
    await click(day("2026-10-05"));
    await click(day("2026-10-12"));
    await click(page.host.querySelector('[data-testid="period-apply"]'));
    assert.deepEqual(page.picked, [{ key: "custom", from: "2026-10-05", to: "2026-10-12" }]);
    assert.equal(page.host.querySelector('[data-testid="period-popover"]'), null, "applying closes it");
  } finally { await page.close(); }
});

test("Escape closes the popover and the bar keeps its period", async () => {
  const page = await mount(1280);
  try {
    await click(page.host.querySelector('[data-segment="custom"]'));
    await act(async () => { document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
    assert.equal(page.host.querySelector('[data-testid="period-popover"]'), null);
    assert.deepEqual(page.picked, []);
    assert.equal(page.host.querySelector('[data-segment="this_month"]')?.getAttribute("aria-checked"), "true");
  } finally { await page.close(); }
});

test("once applied, the segment reads the range, with an en dash and no em dash", async () => {
  const page = await mount(1280, { key: "custom", from: "2026-09-21", to: "2026-10-20" });
  try {
    const segment = page.host.querySelector('[data-segment="custom"]')!;
    assert.match(segment.textContent ?? "", /21 sept?\.? – 20 oct/);
    assert.doesNotMatch(segment.textContent ?? "", /—|Personalizado/);
  } finally { await page.close(); }
});

test("on a phone Personalizado opens the same calendar in a sheet, and an applied range stays its own option", async () => {
  const page = await mount(390, { key: "custom", from: "2026-09-21", to: "2026-10-20" });
  try {
    const select = page.host.querySelector<HTMLSelectElement>("select")!;
    assert.match(select.selectedOptions[0].textContent ?? "", /21 sept?\.? – 20 oct/);
    await act(async () => { select.value = "custom"; select.dispatchEvent(new Event("change", { bubbles: true })); });
    const sheet = document.querySelector('[data-testid="period-sheet"]');
    assert.ok(sheet?.querySelector('[data-testid="range-calendar"]'), "the range calendar in a sheet");
    assert.equal(page.host.querySelector('[data-testid="period-popover"]'), null);
    assert.equal(document.querySelector('input[type="date"]'), null);
  } finally { await page.close(); }
});
