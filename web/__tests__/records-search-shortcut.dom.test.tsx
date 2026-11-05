import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
beforeAll(() => { GlobalRegistrator.register({ url: "http://localhost/biz" }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterAll(() => GlobalRegistrator.unregister());
let cleanup = async () => {};
afterEach(async () => { await cleanup(); document.body.innerHTML = ""; });
test("Records owns Command-K and Ctrl-K only while mounted and without an overlay", async () => {
  const { act, useRef } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { useRecordsSearchShortcut } = await import("@/components/business-app/transacciones/useRecordsSearchShortcut");
  function Harness() { const ref = useRef<HTMLInputElement>(null); useRecordsSearchShortcut(ref); return <input ref={ref} type="search" defaultValue="supplier" />; }
  const host = document.createElement("div"); document.body.append(host); const root = createRoot(host);
  await act(async () => root.render(<Harness />));
  cleanup = async () => { await act(async () => root.unmount()); };
  const input = host.querySelector("input")!;
  const key = (modifiers: KeyboardEventInit) => { const event = new KeyboardEvent("keydown", { key: "k", code: "KeyK", bubbles: true, cancelable: true, ...modifiers }); document.body.dispatchEvent(event); return event; };
  for (const modifiers of [{ metaKey: true }, { ctrlKey: true }]) {
    input.blur(); assert.equal(key(modifiers).defaultPrevented, true); assert.equal(document.activeElement, input); assert.equal(input.selectionStart, 0); assert.equal(input.selectionEnd, 8);
  }
  input.blur(); assert.equal(key({ metaKey: true, shiftKey: true }).defaultPrevented, false);
  const dialog = document.createElement("div"); dialog.setAttribute("role", "dialog"); dialog.setAttribute("aria-modal", "true"); document.body.append(dialog);
  assert.equal(key({ metaKey: true }).defaultPrevented, false); assert.notEqual(document.activeElement, input);
  dialog.remove(); await act(async () => root.render(null));
  assert.equal(key({ metaKey: true }).defaultPrevented, false);
});
