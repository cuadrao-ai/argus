import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

beforeAll(() => { GlobalRegistrator.register({ url: "http://localhost/biz" }); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; });
afterAll(async () => { await GlobalRegistrator.unregister(); });

const SIDE = { width: 100, height: 20 };
async function line(text: string) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const Cut = (await import("@/components/business-app/recepcion/ReceptionCutText")).default;
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => 100 });
  Object.defineProperty(HTMLElement.prototype, "scrollWidth", { configurable: true, get: () => SIDE.width });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => 20 });
  Object.defineProperty(HTMLElement.prototype, "scrollHeight", { configurable: true, get: () => SIDE.height });
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  await act(async () => { root.render(<Cut text={text} data-testid="line" />); });
  return { act, node: () => host.querySelector<HTMLElement>('[data-testid="line"]')!, close: () => act(async () => { root.unmount(); host.remove(); }) };
}
const tip = () => document.querySelector('[role="tooltip"]');
const wait = (act: Awaited<ReturnType<typeof line>>["act"]) => act(async () => { await new Promise(resolve => setTimeout(resolve, 340)); });

test("text that fits takes no focus and no tooltip", async () => {
  SIDE.width = 100; SIDE.height = 20;
  const page = await line("Falta el RNC");
  assert.equal(page.node().getAttribute("tabindex"), null);
  await page.act(async () => { page.node().dispatchEvent(new MouseEvent("mouseover", { bubbles: true })); });
  await wait(page.act);
  assert.equal(tip(), null);
  await page.close();
});

test("cut-off text takes keyboard focus and shows the full text on it", async () => {
  SIDE.width = 240; SIDE.height = 20;
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

test("a line the clamp cut takes keyboard focus, as one cut by width does", async () => {
  SIDE.width = 100; SIDE.height = 40;
  const page = await line("Juan Carlos Adán Dueñas Martínez");
  assert.equal(page.node().getAttribute("tabindex"), "0");
  await page.close();
});

test("Bandeja cuts its tooltip lines with a clamp, so Safari adds no second tooltip", async () => {
  const { readFileSync } = await import("node:fs");
  const css = readFileSync(new URL("../components/business-app/recepcion/reception.module.css", import.meta.url), "utf8");
  const clamp = css.split("\n").find(rule => rule.includes("-webkit-line-clamp:1"));
  for (const name of ["title", "sender", "deletedName", "deletedActorName"]) {
    assert.match(clamp ?? "", new RegExp(`\\.${name}[,\\s]`), name);
    for (const rule of css.split("\n").filter(rule => new RegExp(`\\.${name}\\b[^{]*\\{`).test(rule))) assert.doesNotMatch(rule, /text-overflow:ellipsis/, rule);
  }
});
