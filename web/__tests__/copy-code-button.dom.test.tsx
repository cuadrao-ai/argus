import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

// A real DOM for the clicks, the timer and the unmount; registered for this
// file only and released at the end.
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const SHOW_MS = 40;

async function mount(options: { clipboard: boolean; execCommand: boolean }) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const { default: CopyCodeButton } = await import("../components/settings/CopyCodeButton");
  const written: string[] = [];
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: options.clipboard
      ? { writeText: async (value: string) => { written.push(value); } }
      : { writeText: async () => { throw new Error("denied"); } },
  });
  document.execCommand = () => options.execCommand;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } } });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <I18nextProvider i18n={i18n}>
        <CopyCodeButton text="CUADRAO ABCD1234" showCheckMs={SHOW_MS} />
      </I18nextProvider>,
    );
  });
  const button = host.querySelector("button")!;
  const status = () => host.querySelector('[role="status"]')!;
  const click = () => act(async () => { button.click(); await Promise.resolve(); });
  const wait = (ms: number) => act(async () => { await new Promise((resolve) => setTimeout(resolve, ms)); });
  return { act, root, host, button, status, click, wait, written };
}

describe("the copy button in a real DOM", () => {
  test("a press copies the full code, shows the check, announces Copiado, and returns after the delay", async () => {
    const page = await mount({ clipboard: true, execCommand: false });
    assert.equal(page.button.getAttribute("aria-label"), "Copiar código");
    assert.equal(page.button.getAttribute("data-state"), "idle");
    await page.click();
    assert.deepEqual(page.written, ["CUADRAO ABCD1234"]);
    assert.equal(page.button.getAttribute("data-state"), "copied");
    assert.ok(page.host.querySelector('[data-icon="check"]'));
    assert.equal(page.status().textContent, "Copiado");
    await page.wait(SHOW_MS + 20);
    assert.equal(page.button.getAttribute("data-state"), "idle");
    assert.ok(page.host.querySelector('[data-icon="copy"]'));
    assert.equal(page.status().textContent, "");
    await page.act(async () => page.root.unmount());
  });

  test("a second press within the delay re-announces through a new live region", async () => {
    const page = await mount({ clipboard: true, execCommand: false });
    await page.click();
    const first = page.status();
    assert.equal(first.getAttribute("data-presses"), "1");
    await page.click();
    const second = page.status();
    assert.notEqual(first, second);
    assert.equal(second.getAttribute("data-presses"), "2");
    assert.equal(second.textContent, "Copiado");
    assert.equal(page.button.getAttribute("data-state"), "copied");
    await page.act(async () => page.root.unmount());
  });

  test("a clipboard that refuses and a fallback that fails show no false check and say so", async () => {
    const page = await mount({ clipboard: false, execCommand: false });
    await page.click();
    assert.equal(page.button.getAttribute("data-state"), "failed");
    assert.equal(page.host.querySelector('[data-icon="check"]'), null);
    assert.ok(page.host.querySelector('[data-icon="copy"]'));
    assert.equal(page.status().textContent, "No se pudo copiar. Selecciona el texto para copiarlo.");
    await page.act(async () => page.root.unmount());
  });

  test("a refusing clipboard still copies through the selection fallback when the document allows it", async () => {
    const page = await mount({ clipboard: false, execCommand: true });
    await page.click();
    assert.equal(page.button.getAttribute("data-state"), "copied");
    assert.equal(page.status().textContent, "Copiado");
    await page.act(async () => page.root.unmount());
  });

  test("unmounting before the delay clears the timer", async () => {
    const page = await mount({ clipboard: true, execCommand: false });
    const original = globalThis.clearTimeout;
    let cleared = 0;
    globalThis.clearTimeout = ((id: Parameters<typeof clearTimeout>[0]) => { cleared += 1; return original(id); }) as typeof clearTimeout;
    try {
      await page.click();
      await page.act(async () => page.root.unmount());
      assert.ok(cleared >= 1);
    } finally {
      globalThis.clearTimeout = original;
    }
    await page.wait(SHOW_MS + 20);
  });
});
