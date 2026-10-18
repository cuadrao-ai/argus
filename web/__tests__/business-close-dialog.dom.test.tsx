import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import BusinessCloseDialog, { businessCloseCopyEs, type BusinessCloseState } from "@/components/business-app/BusinessCloseDialog";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function mount() {
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  const confirmed: string[] = [];
  let cancelled = 0;
  let exported = 0;
  const render = async (state: BusinessCloseState = { kind: "idle" }, name = "Taller Luna") => {
    await act(async () => root.render(<BusinessCloseDialog businessName={name} copy={businessCloseCopyEs} state={state} onConfirm={(name) => { confirmed.push(name); }} onCancel={() => { cancelled++; }} exportControl={<button type="button" onClick={() => { exported++; }}>{businessCloseCopyEs.download}</button>} />));
  };
  await render();
  const button = (text: string) => { const found = [...document.querySelectorAll("button")].find((item) => item.textContent === text); assert.ok(found); return found; };
  const enter = async (value: string) => { const input = document.querySelector("input"); assert.ok(input); await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value); input.dispatchEvent(new Event("input", { bubbles: true })); }); };
  return { confirmed, render, button, enter, cancelled: () => cancelled, exported: () => exported, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

test("the dialog keeps the exact approved copy and independent export control", async () => {
  const view = await mount();
  try {
    for (const text of Object.values(businessCloseCopyEs)) assert.ok(document.body.textContent?.includes(text));
    await act(async () => view.button(businessCloseCopyEs.download).click());
    assert.equal(view.exported(), 1);
    assert.deepEqual(view.confirmed, []);
    await act(async () => view.button(businessCloseCopyEs.cancel).click());
    assert.equal(view.cancelled(), 1);
  } finally { await view.close(); }
});

test("close requires the exact current name without trimming or case folding", async () => {
  const view = await mount();
  try {
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
