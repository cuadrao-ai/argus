import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => 600 });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => 500 });
  Object.defineProperty(HTMLElement.prototype, "offsetParent", { configurable: true, get() { return this.parentElement; } });
  HTMLElement.prototype.setPointerCapture = () => undefined;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function setup(sourceId = "a", imageSize = { width: 1200, height: 2000 }, viewport = { width: 600, height: 500 }) {
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => viewport.width });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => viewport.height });
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { default: Viewer } = await import("@/components/business-app/ReceiptImageZoom");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const revoked: string[] = [];
  let created = 0;
  const originalCreate = URL.createObjectURL;
  const originalRevoke = URL.revokeObjectURL;
  URL.createObjectURL = () => `blob:receipt-${++created}`;
  URL.revokeObjectURL = (url) => { revoked.push(url); };
  const blob = new Blob(["receipt"], { type: "image/png" });
  const render = async (id: string, file = blob) => {
    await act(async () => root.render(<I18nextProvider i18n={i18n}><Viewer src="data:image/png;base64,AA==" blob={file} sourceId={id} alt="Comprobante original" /></I18nextProvider>));
    const image = document.querySelector("img")!;
    Object.defineProperty(image, "naturalWidth", { configurable: true, value: imageSize.width });
    Object.defineProperty(image, "naturalHeight", { configurable: true, value: imageSize.height });
    await act(async () => image.dispatchEvent(new Event("load")));
  };
  await render(sourceId);
  const button = (name: string) => document.querySelector<HTMLButtonElement>(`button[aria-label="${name}"]`)!;
  const click = (name: string) => act(async () => button(name).click());
  const well = () => document.querySelector<HTMLElement>('[data-testid="receipt-image-zoom"]')!;
  const key = (value: string, target: HTMLElement = well(), shiftKey = false) => act(async () => { target.focus(); target.dispatchEvent(new KeyboardEvent("keydown", { key: value, shiftKey, bubbles: true, cancelable: true })); });
  const cleanup = async () => {
    await act(async () => root.unmount()); host.remove();
    URL.createObjectURL = originalCreate; URL.revokeObjectURL = originalRevoke;
  };
  return { act, host, render, button, click, well, key, cleanup, revoked };
}

test("fit geometry uses intrinsic size, swaps rotated dimensions and bounds manual zoom", async () => {
  const { receiptScale } = await import("@/components/business-app/ReceiptImageZoom");
  const image = { width: 1200, height: 2000 }, viewport = { width: 600, height: 500 };
  assert.equal(receiptScale({ kind: "fit-page" }, image, viewport, 0), 0.25);
  assert.equal(receiptScale({ kind: "fit-page" }, image, viewport, 1), 0.3);
  assert.equal(receiptScale({ kind: "fit-width" }, image, viewport, 0), 0.5);
  assert.equal(receiptScale({ kind: "manual", scale: 9 }, image, viewport, 0), 5);
  assert.equal(receiptScale({ kind: "manual", scale: 0.01 }, image, viewport, 0), 0.25);
  assert.equal(receiptScale({ kind: "manual", scale: 0 }, image, viewport, 0), 0.25);
});

for (const turns of [0, 1]) {
  test(`large photo fit presets use viewport geometry at ${turns * 90} degrees`, async () => {
    const env = await setup(`large-photo-${turns}`, { width: 3024, height: 4032 }, { width: 375, height: 300 });
    try {
      if (turns) await env.click("Girar a la derecha");
      const image = document.querySelector("img")!;
      const assertDimensions = (scale: number) => {
        assert.equal(Number(env.well().dataset.zoom), scale);
        assert.equal(parseFloat(image.style.width), 3024 * scale);
        assert.equal(parseFloat(image.style.height), 4032 * scale);
      };
      const width = turns ? 4032 : 3024;
      const height = turns ? 3024 : 4032;
      const pageScale = Math.min(375 / width, 300 / height);
      assertDimensions(pageScale);
      assert.equal((env.well().firstElementChild as HTMLElement).style.width, "375px");
      assert.equal((env.well().firstElementChild as HTMLElement).style.height, "300px");
      assert.equal(env.button("Alejar").disabled, true);
      await env.click("Ajustar al ancho");
      assertDimensions(375 / width);
      assert.equal(env.button("Alejar").disabled, 375 / width === pageScale);
      await env.key("-");
      assert.equal(env.well().dataset.fit, "fit-page");
      assertDimensions(pageScale);
    } finally { await env.cleanup(); }
  });
}

test("fit presets also remain exact above the manual maximum", async () => {
  const { receiptScale } = await import("@/components/business-app/ReceiptImageZoom");
  assert.equal(receiptScale({ kind: "fit-page" }, { width: 10, height: 20 }, { width: 375, height: 300 }, 0), 15);
  assert.equal(receiptScale({ kind: "fit-width" }, { width: 10, height: 20 }, { width: 375, height: 300 }, 0), 37.5);
});

for (const input of ["button", "keyboard", "wheel", "pinch"]) {
  test(`${input} zoom out reaches the large photo fit scale through the manual minimum`, async () => {
    const env = await setup(`large-out-${input}`, { width: 3024, height: 4032 }, { width: 375, height: 300 });
    try {
      const pointer = (type: string, id: number, x: number) => env.act(async () => env.well().dispatchEvent(new PointerEvent(type, { pointerId: id, pointerType: "touch", clientX: x, clientY: 100, bubbles: true })));
      const out = async () => {
        if (input === "button") await env.click("Alejar");
        else if (input === "keyboard") await env.key("-");
        else if (input === "wheel") {
          const event = new WheelEvent("wheel", { deltaY: 200, cancelable: true });
          Object.defineProperty(event, "ctrlKey", { value: true });
          await env.act(async () => env.well().dispatchEvent(event));
        } else {
          await pointer("pointerdown", 1, 100);
          await pointer("pointerdown", 2, 300);
          await pointer("pointermove", 2, 120);
          await pointer("pointerup", 1, 100);
          await pointer("pointerup", 2, 120);
        }
      };
      await env.click("Ajustar al ancho");
      await env.click("Tamaño real");
      for (let i = 0; i < 4 && Number(env.well().dataset.zoom) > 0.25; i++) await out();
      assert.equal(env.well().dataset.zoom, "0.25");
      assert.equal(env.well().dataset.fit, "manual");
      assert.equal(env.button("Alejar").disabled, false);
      await out();
      assert.equal(env.well().dataset.fit, "fit-page");
      assert.equal(Number(env.well().dataset.zoom), 300 / 4032);
      assert.equal(env.button("Alejar").disabled, true);
      await env.click("Ajustar al ancho");
      await out();
      assert.equal(env.well().dataset.fit, "fit-page");
      assert.equal(Number(env.well().dataset.zoom), 300 / 4032);
    } finally { await env.cleanup(); }
  });
}

test("rotation entries validate, promote on open and evict the least recent of 200 IDs", async () => {
  const { readReceiptRotations, rememberReceiptRotation } = await import("@/components/business-app/ReceiptImageZoom");
  const { writeStored, removeStored } = await import("@/lib/browser-storage");
  writeStored("cuadrao:receipt_rotations:v1", JSON.stringify([null, { id: "bad", turns: 8 }, { id: "ok", turns: 3 }]));
  assert.deepEqual(readReceiptRotations(), [{ id: "ok", turns: 3 }]);
  removeStored("cuadrao:receipt_rotations:v1");
  for (let i = 0; i < 200; i++) rememberReceiptRotation(`r${i}`, i % 4);
  rememberReceiptRotation("r0");
  rememberReceiptRotation("r200", -1);
  const entries = readReceiptRotations();
  assert.equal(entries.length, 200);
  assert.equal(entries.some(({ id }) => id === "r1"), false);
  assert.equal(entries.some(({ id }) => id === "r0"), true);
  assert.equal(entries.at(-1)?.turns, 3);
  const original = Object.getOwnPropertyDescriptor(window, "localStorage");
  Object.defineProperty(window, "localStorage", { configurable: true, get() { throw new Error("blocked"); } });
  assert.doesNotThrow(() => rememberReceiptRotation("blocked", 2));
  assert.deepEqual(readReceiptRotations(), []);
  if (original) Object.defineProperty(window, "localStorage", original);
  removeStored("cuadrao:receipt_rotations:v1");
});

test("each source opens fit page, keeps only its rotation, and owns the original Blob URL", async () => {
  const env = await setup();
  try {
    assert.equal(env.well().dataset.fit, "fit-page");
    await env.click("Girar a la derecha");
    await env.key("+");
    assert.equal(env.well().dataset.rotation, "90");
    assert.equal(env.well().dataset.fit, "manual");
    await env.render("b");
    assert.equal(env.well().dataset.rotation, "0");
    assert.equal(env.well().dataset.fit, "fit-page");
    await env.render("a");
    assert.equal(env.well().dataset.rotation, "90");
    assert.equal(env.well().dataset.fit, "fit-page");
    assert.ok(env.revoked.includes("blob:receipt-1"));
    assert.equal(document.querySelector('a[aria-label="Abrir original"]')?.getAttribute("target"), "_blank");
  } finally { await env.cleanup(); }
  assert.equal(env.revoked.length, 3);
});

test("focused shortcuts, continuous pointer zoom, and double click respect zoom bounds", async () => {
  const env = await setup("gestures");
  try {
    const outside = document.createElement("input"); document.body.append(outside);
    await env.key("r", outside);
    assert.equal(env.well().dataset.rotation, "0");
    outside.remove();
    await env.key("r"); await env.key("R", env.well(), true);
    assert.equal(env.well().dataset.rotation, "0");
    const normal = new WheelEvent("wheel", { deltaY: -100, cancelable: true });
    await env.act(async () => env.well().dispatchEvent(normal));
    assert.equal(normal.defaultPrevented, false);
    const pinch = new WheelEvent("wheel", { deltaY: -30, ctrlKey: true, clientX: 100, clientY: 100, cancelable: true });
    Object.defineProperty(pinch, "ctrlKey", { value: true });
    await env.act(async () => env.well().dispatchEvent(pinch));
    assert.equal(pinch.defaultPrevented, true);
    assert.ok(Number(env.well().dataset.zoom) > 0.25);
    for (let i = 0; i < 24; i++) await env.key("+");
    assert.equal(env.well().dataset.zoom, "5");
    assert.equal(env.button("Acercar").disabled, true);
    await env.act(async () => env.well().dispatchEvent(new MouseEvent("dblclick", { bubbles: true, clientX: 100, clientY: 100 })));
    assert.equal(env.well().dataset.fit, "fit-page");
    for (let i = 0; i < 4; i++) await env.key("r");
    assert.ok(document.querySelector("img")!.style.transform.includes("rotate(360deg)"));
  } finally { await env.cleanup(); }
});

test("touch pinch follows the moving midpoint and pointer dragging pans oversized images", async () => {
  const env = await setup("touch");
  try {
    await env.click("Ajustar al ancho");
    await env.click("Tamaño real");
    const well = env.well();
    well.scrollLeft = 600; well.scrollTop = 600;
    const pointer = (type: string, id: number, x: number, y: number) => env.act(async () => well.dispatchEvent(new PointerEvent(type, { pointerId: id, pointerType: "touch", clientX: x, clientY: y, bubbles: true })));
    await pointer("pointerdown", 1, 200, 200);
    await pointer("pointerdown", 2, 400, 200);
    await pointer("pointermove", 1, 220, 220);
    await pointer("pointermove", 2, 420, 220);
    assert.ok(Math.abs(Number(well.dataset.zoom) - 1) < 0.00001);
    assert.ok(Math.abs(well.scrollLeft - 580) < 0.01);
    assert.ok(Math.abs(well.scrollTop - 580) < 0.01);
    await pointer("pointerup", 2, 420, 220);
    await pointer("pointermove", 1, 240, 240);
    assert.ok(Math.abs(well.scrollLeft - 560) < 0.01);
    assert.ok(Math.abs(well.scrollTop - 560) < 0.01);
    await pointer("pointerup", 1, 240, 240);
    await pointer("pointerdown", 3, 240, 240);
    await pointer("pointercancel", 3, 240, 240);
    await pointer("pointermove", 3, 300, 300);
    assert.ok(Math.abs(well.scrollLeft - 560) < 0.01);
    assert.ok(Math.abs(well.scrollTop - 560) < 0.01);
  } finally { await env.cleanup(); }
});

test("a pinch at the zoom limit still follows its midpoint", async () => {
  const env = await setup("clamped-touch");
  try {
    for (let i = 0; i < 24; i++) await env.key("+");
    const well = env.well();
    well.scrollLeft = 1000; well.scrollTop = 1000;
    const pointer = (type: string, id: number, x: number, y: number) => env.act(async () => well.dispatchEvent(new PointerEvent(type, { pointerId: id, pointerType: "touch", clientX: x, clientY: y, bubbles: true })));
    await pointer("pointerdown", 1, 200, 200);
    await pointer("pointerdown", 2, 400, 200);
    await pointer("pointermove", 1, 180, 200);
    assert.equal(well.dataset.zoom, "5");
    assert.equal(well.scrollLeft, 1010);
    await pointer("pointermove", 2, 420, 200);
    assert.equal(well.dataset.zoom, "5");
    assert.equal(well.scrollLeft, 1000);
    await pointer("pointermove", 1, 180, 240);
    assert.equal(well.dataset.zoom, "5");
    assert.equal(well.scrollTop, 980);
    await pointer("pointerup", 1, 180, 240);
    await pointer("pointerup", 2, 420, 200);
    well.scrollLeft = 1000; well.scrollTop = 1000;
    await pointer("pointerdown", 1, 200, 200);
    await pointer("pointerdown", 2, 400, 200);
    await pointer("pointermove", 1, 400, 400);
    assert.equal(well.dataset.zoom, "5");
    assert.equal(well.scrollLeft, 900);
    assert.equal(well.scrollTop, 900);
  } finally { await env.cleanup(); }
});

test("keyboard full window returns to the same well or toolbar control", async () => {
  const env = await setup("focus-return");
  try {
    await env.key("f");
    await env.key("Escape");
    assert.equal(document.activeElement, env.well());
    await env.key("f", env.button("Girar a la derecha"));
    await env.key("Escape");
    assert.equal(document.activeElement, env.button("Girar a la derecha"));
  } finally { await env.cleanup(); }
});

test("full window overlay traps focus, shows a real toolbar tooltip, and restores focus on Escape", async () => {
  const env = await setup("overlay");
  try {
    await env.act(async () => { env.button("Pantalla completa").focus(); env.button("Pantalla completa").click(); });
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]')!;
    assert.equal(dialog.getAttribute("aria-modal"), "true");
    assert.ok(dialog.className.includes("z-[9000]"));
    assert.equal(document.querySelectorAll('[data-testid="receipt-viewer-toolbar"]').length, 1);
    const original = dialog.querySelector<HTMLAnchorElement>('a[aria-label="Abrir original"]')!;
    await env.act(async () => { original.focus(); original.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true })); });
    assert.equal(document.activeElement, env.well());
    await env.act(async () => { env.button("Girar a la derecha").dispatchEvent(new MouseEvent("mouseover", { bubbles: true })); await new Promise((resolve) => setTimeout(resolve, 350)); });
    const tooltip = document.querySelector<HTMLElement>('[role="tooltip"]');
    assert.ok(tooltip?.textContent?.includes("Girar a la derecha (R)"));
    assert.equal(tooltip?.style.visibility, "visible");
    assert.equal(tooltip?.style.zIndex, "9999");
    await env.key("Escape");
    assert.equal(document.querySelector('[role="dialog"]'), null);
    assert.equal(document.activeElement, env.button("Pantalla completa"));
  } finally { await env.cleanup(); }
});
