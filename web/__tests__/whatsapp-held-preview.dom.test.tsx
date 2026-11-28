import assert from "node:assert/strict";
import { test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

test("held photo thumbnails load on visibility or first open, then restore focus on every dismissal", async () => {
  GlobalRegistrator.register({ url: "http://localhost" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  Object.defineProperty(HTMLElement.prototype, "offsetParent", { configurable: true, get() { return this.parentElement; } });

  const { act, StrictMode } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { WhatsAppHeldFilePreview } = await import("@/components/settings/WhatsAppHeldFilePreview");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const previousFetch = globalThis.fetch;
  const previousAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true";
  const previousObserver = globalThis.IntersectionObserver;
  const visible = new Map<Element, () => void>();
  globalThis.IntersectionObserver = class extends IntersectionObserver {
    constructor(private callback: IntersectionObserverCallback) { super(callback); }
    observe(element: Element) {
      visible.set(element, () => this.callback([{ target: element, isIntersecting: true } as IntersectionObserverEntry], this));
    }
  };
  const requests: string[] = [];
  const previewUrl = "/api/v1/whatsapp/held-files/synthetic/preview";
  globalThis.fetch = (async (input: string | URL | Request) => {
    requests.push(new URL(String(input), location.origin).pathname);
    return new Response(new Blob(["synthetic"], { type: "image/png" }));
  }) as typeof fetch;
  try {
    await act(async () => root.render(<StrictMode><I18nextProvider i18n={i18n}><WhatsAppHeldFilePreview
      id="synthetic" mediaType="image/png" previewUrl={previewUrl}
    ><span>Sin RNC del comprador</span></WhatsAppHeldFilePreview><WhatsAppHeldFilePreview
      id="visible" mediaType="image/jpeg" previewUrl="/api/v1/whatsapp/held-files/visible/preview"
    ><span>Sin leer</span></WhatsAppHeldFilePreview></I18nextProvider></StrictMode>));
    const thumb = host.querySelector<HTMLButtonElement>('button[aria-label="Vista previa"]')!;
    const title = host.querySelector<HTMLButtonElement>('button[tabindex="-1"]')!;
    assert.equal(title.textContent, "Sin RNC del comprador");
    assert.deepEqual(requests, []);
    const visibleThumb = host.querySelectorAll<HTMLButtonElement>('button[aria-label="Vista previa"]')[1];
    await act(async () => visible.get(visibleThumb)!());
    assert.deepEqual(requests, ["/api/v1/whatsapp/held-files/visible/preview"]);
    for (const [trigger, exit] of [[title, "f"], [thumb, "Escape"], [thumb, "button"]] as const) {
      await act(async () => { trigger.focus(); trigger.click(); });
      await act(async () => { await new Promise(resolve => setTimeout(resolve, 30)); });
      const dialog = document.querySelector<HTMLElement>('[role="dialog"][aria-label="Recibo original"]')!;
      assert.ok(dialog?.querySelector('[data-fit="fit-page"]'));
      const close = dialog.querySelector<HTMLButtonElement>('button[aria-label="Salir de pantalla completa"]')!;
      assert.equal(document.activeElement, close);
      await act(async () => {
        if (exit === "button") close.click();
        else close.dispatchEvent(new KeyboardEvent("keydown", { key: exit, bubbles: true, cancelable: true }));
      });
      assert.equal(document.querySelector('[role="dialog"]'), null);
      assert.equal(document.activeElement, thumb);
    }
    assert.deepEqual(requests, ["/api/v1/whatsapp/held-files/visible/preview", previewUrl]);
  } finally {
    await act(async () => root.unmount());
    host.remove();
    globalThis.fetch = previousFetch;
    globalThis.IntersectionObserver = previousObserver;
    if (previousAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    else process.env.NEXT_PUBLIC_MOCK_AUTH = previousAuth;
    await GlobalRegistrator.unregister();
  }
});
