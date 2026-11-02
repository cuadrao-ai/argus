import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

beforeAll(() => { GlobalRegistrator.register({ url: "http://localhost/biz" }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterAll(async () => { await GlobalRegistrator.unregister(); });

const SIDE = { width: 100 };
async function line(text: string) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const Cut = (await import("@/components/business-app/recepcion/ReceptionCutText")).default;
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => 100 });
  Object.defineProperty(HTMLElement.prototype, "scrollWidth", { configurable: true, get: () => SIDE.width });
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  await act(async () => { root.render(<Cut text={text} data-testid="line" />); });
  return { act, node: () => host.querySelector<HTMLElement>('[data-testid="line"]')!, close: () => act(async () => { root.unmount(); host.remove(); }) };
}
const tip = () => document.querySelector('[role="tooltip"]');
const wait = (act: Awaited<ReturnType<typeof line>>["act"]) => act(async () => { await new Promise(resolve => setTimeout(resolve, 340)); });

test("text that fits takes no focus and no tooltip", async () => {
  SIDE.width = 100;
  const page = await line("Falta el RNC");
  assert.equal(page.node().getAttribute("tabindex"), null);
  await page.act(async () => { page.node().dispatchEvent(new MouseEvent("mouseover", { bubbles: true })); });
  await wait(page.act);
  assert.equal(tip(), null);
  await page.close();
});

test("cut-off text takes keyboard focus and shows the full text on it", async () => {
  SIDE.width = 240;
  const page = await line("Este tipo de archivo no se puede guardar como recibo");
  assert.equal(page.node().getAttribute("tabindex"), "0");
  const matches = HTMLElement.prototype.matches;
  HTMLElement.prototype.matches = function (selector: string) { return selector === ":focus-visible" ? true : matches.call(this, selector); };
  await page.act(async () => { page.node().focus(); });
  await wait(page.act);
  HTMLElement.prototype.matches = matches;
  assert.equal(tip()?.textContent, "Este tipo de archivo no se puede guardar como recibo");
  await page.act(async () => { page.node().blur(); });
  assert.equal(tip(), null);
  await page.close();
});
