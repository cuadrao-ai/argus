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

async function mount(width: number) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 900 });
  const { default: BusinessPeriodControl } = await import("@/components/business-app/BusinessPeriodControl");
  const picked: (PeriodKey | Period)[] = [];
  const period: Period = { key: "this_month", from: "2026-10-01", to: "2026-10-31" } as Period;
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => root.render(<BusinessPeriodControl period={period} setPeriod={(next) => picked.push(next)} />));
  return { host, picked, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

test("on a phone the period is one native picker that fits any width, never a bar that runs off the screen", async () => {
  const page = await mount(390);
  try {
    assert.equal(page.host.querySelector('[role="radiogroup"], [data-testid="segmented-control"]'), null, "no segmented bar on a phone");
    const select = page.host.querySelector<HTMLSelectElement>("select");
    assert.ok(select, "a native picker");
    assert.equal(select.options.length, 5);
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
