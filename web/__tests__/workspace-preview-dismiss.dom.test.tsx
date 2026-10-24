import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, mock, spyOn, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";

const emailSource = { emailIntake: async () => ({ enabled: true, receiving_address: "shared@receipts.example.test" }) };
mock.module("@/components/business-app/BusinessWorkspace", () => ({
  useBusiness: () => ({ actions: { create: [] }, chosen: null, revision: 0, source: emailSource }),
}));
const cleanups: (() => Promise<void>)[] = [];
beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterEach(async () => {
  for (const cleanup of cleanups.splice(0)) await cleanup();
  (await import("@/components/layout/overlayStack")).resetOverlayStack();
  document.body.innerHTML = "";
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function mount() {
  const contentWindow = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, "contentWindow")!;
  const source = { postMessage() {} } as unknown as Window;
  Object.defineProperty(HTMLIFrameElement.prototype, "contentWindow", { configurable: true, get: () => source });
  cleanups.push(async () => { Object.defineProperty(HTMLIFrameElement.prototype, "contentWindow", contentWindow); });
  const setAttribute = HTMLIFrameElement.prototype.setAttribute;
  const iframeSource = spyOn(HTMLIFrameElement.prototype, "setAttribute").mockImplementation(function (this: HTMLIFrameElement, name, value) {
    setAttribute.call(this, name, name === "src" ? "about:blank" : value);
  });
  cleanups.push(async () => { iframeSource.mockRestore(); });
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { default: Preview } = await import("@/app/design-workspace/WorkspaceSetupPreview");
  const i18n = createInstance();
  await i18n.init({ lng: "en", resources: {} });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => root.render(<I18nextProvider i18n={i18n}><Preview /></I18nextProvider>));
  cleanups.push(async () => { await act(async () => root.unmount()); });
  const frame = host.querySelector("iframe")!;
  assert.ok(frame.contentWindow);
  const send = async (origin = location.origin, source: MessageEventSource | null = frame.contentWindow) => {
    await act(async () => window.dispatchEvent(new MessageEvent("message", {
      origin, source, data: { type: "workspace-preview-pointerdown" },
    })));
  };
  const refresh = async () => {
    await act(async () => window.dispatchEvent(new MessageEvent("message", {
      origin: location.origin, source: frame.contentWindow, data: { type: "workspace-preview-render" },
    })));
  };
  return { host, frame, send, refresh };
}

test("a guide press dismisses the outside menu through the overlay registry", async () => {
  const { frame, send } = await mount();
  const { registerOverlayLayer } = await import("@/components/layout/overlayStack");
  const menu = document.createElement("div");
  document.body.appendChild(menu);
  let dismissed = false;
  registerOverlayLayer({ id: "settings", containerRef: { current: menu }, trapFocus: false,
    onOutsidePointerDown: (event) => { assert.equal(event.target, frame); dismissed = true; },
  });
  await send();
  assert.equal(dismissed, true);
});

test("untrusted origins and unrelated windows cannot dismiss the menu", async () => {
  const { send } = await mount();
  const { registerOverlayLayer } = await import("@/components/layout/overlayStack");
  let dismissals = 0;
  registerOverlayLayer({ id: "settings", containerRef: { current: null }, trapFocus: false,
    onOutsidePointerDown: () => { dismissals += 1; },
  });
  await send("https://untrusted.example");
  await send(location.origin, window);
  await send(location.origin, null);
  assert.equal(dismissals, 0);
});

test("a frame press stays inside its enclosing overlay without dismissing lower menus", async () => {
  const { host, send } = await mount();
  const { registerOverlayLayer } = await import("@/components/layout/overlayStack");
  const dismissed: string[] = [];
  registerOverlayLayer({ id: "settings", containerRef: { current: null }, trapFocus: false,
    onOutsidePointerDown: () => dismissed.push("settings"),
  });
  registerOverlayLayer({ id: "dossier", containerRef: { current: host }, trapFocus: true,
    onOutsidePointerDown: () => dismissed.push("dossier"),
  });
  await send();
  assert.deepEqual(dismissed, []);
});


test("outside dismissal still works after returning from a settings child layer", async () => {
  const { send } = await mount();
  const { registerOverlayLayer, unregisterOverlayLayer } = await import("@/components/layout/overlayStack");
  const dismissed: string[] = [];
  registerOverlayLayer({ id: "settings", containerRef: { current: null }, trapFocus: false,
    onOutsidePointerDown: () => dismissed.push("settings"),
  });
  registerOverlayLayer({ id: "preferences", containerRef: { current: null }, trapFocus: true,
    onOutsidePointerDown: () => dismissed.push("preferences"),
  });
  unregisterOverlayLayer("preferences");
  await send();
  assert.deepEqual(dismissed, ["settings"]);
});

for (const [label, copied] of [["Copy address", "Address copied."], ["Copiar dirección", "Dirección copiada."]]) {
  test(`the preview inherits button styles and the shared copy behavior: ${label}`, async () => {
    const { frame, refresh } = await mount();
    const doc = frame.contentDocument!;
    doc.body.innerHTML = `<button class="primary">Save</button><button data-button-level="secondary">Cancel</button><span data-copy-value="test@receipts.example.test" data-copy-label="${label}" data-copy-success="${copied}" data-copy-error="Copy failed"></span>`;
    await refresh();
    const { secondaryButtonClass, primaryButtonClass } = await import("@/components/business-app/business-ui");
    assert.equal(doc.querySelector('button')!.className, `${primaryButtonClass} text-[16px]`);
    assert.equal(doc.querySelector('[data-button-level="secondary"]')!.className, `${secondaryButtonClass} text-[16px]`);
    const copy = doc.querySelector<HTMLButtonElement>('[data-copy-state]')!;
    assert.equal(copy.textContent, label);
    assert.equal(copy.className, secondaryButtonClass);
    const writes: string[] = [];
    const clipboard = spyOn(navigator.clipboard, "writeText").mockImplementation(async text => { writes.push(text); });
    cleanups.push(async () => clipboard.mockRestore());
    const { act } = await import("react");
    await act(async () => copy.click());
    assert.deepEqual(writes, ["test@receipts.example.test"]);
    assert.equal(copy.dataset.copyState, "copied");
    assert.equal(doc.querySelector('[role="status"]')!.textContent, copied);
    assert.equal(copy.textContent, label);
    await refresh();
    assert.equal(doc.querySelectorAll('[data-copy-state]').length, 1);
  });
}


test("email in the guide reuses the Business receiving address", async () => {
  const { frame, refresh } = await mount();
  frame.contentDocument!.body.innerHTML = '<div data-business-email></div>';
  await refresh();
  assert.match(frame.contentDocument!.body.textContent!, /shared@receipts.example.test/);
  assert.equal(frame.contentDocument!.querySelectorAll('[data-testid="email-copy-address"]').length, 1);
  assert.equal(frame.contentDocument!.querySelector('input'), null);
});
