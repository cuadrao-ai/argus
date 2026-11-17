import assert from "node:assert/strict";
import { afterAll, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";

// The DOM runner has no canvas renderer or worker. Keep the viewer and source
// selection real; provide two differently sized pages at the rendering boundary.
mock.module("@/components/business-app/receipt-pdf-renderer", () => ({
  loadReceiptPdf: async () => ({
    pageCount: 2,
    drawPage: async (page: number, canvas: HTMLCanvasElement) => {
      canvas.width = page === 1 ? 600 : 400;
      canvas.height = 800;
      return { width: canvas.width, height: canvas.height };
    },
    destroy: async () => {},
  }),
}));

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost", settings: { disableIframePageLoading: true } });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => 600 });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => 500 });
  HTMLCanvasElement.prototype.getContext = (() => ({})) as typeof HTMLCanvasElement.prototype.getContext;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

async function setup(mediaType: string) {
  const { act } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { default: Source } = await import("@/components/business-app/ReceiptSourcePreview");
  const { I18nextProvider } = await import("react-i18next");
  const i18n = (await import("i18next")).default.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: (await import("@/public/locales/es-419/common.json")).default } } });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const originalCreate = URL.createObjectURL;
  const originalRevoke = URL.revokeObjectURL;
  URL.createObjectURL = () => "blob:original-receipt";
  URL.revokeObjectURL = () => {};
  const value = {
    source: { mode: "live", receiptSource: async () => new Blob(["synthetic receipt"], { type: mediaType }) },
    openPanel() {},
  } as unknown as BusinessContextValue;
  const detail = { id: `source-${mediaType}`, media_type: mediaType, filename: "comprobante", received_at: "2026-10-13T17:14:00Z", channel: "web" as const };
  await act(async () => root.render(<I18nextProvider i18n={i18n}><BusinessContext.Provider value={value}><Source detail={detail} initialExpanded /></BusinessContext.Provider></I18nextProvider>));
  const settle = async () => { await act(async () => { await new Promise(resolve => setTimeout(resolve, 30)); }); };
  await settle();
  const button = (name: string) => host.querySelector<HTMLButtonElement>(`button[aria-label="${name}"]`);
  const cleanup = async () => {
    await act(async () => root.unmount());
    host.remove();
    URL.createObjectURL = originalCreate;
    URL.revokeObjectURL = originalRevoke;
  };
  return { host, act, settle, button, cleanup };
}

test("a live PDF source uses our controls without a browser iframe", async () => {
  const env = await setup("application/pdf");
  try {
    assert.equal(env.host.querySelectorAll("iframe").length, 0);
    assert.equal(env.host.querySelectorAll('[data-testid="receipt-viewer-toolbar"]').length, 1);
    for (const name of ["Girar a la izquierda", "Girar a la derecha", "Alejar", "Acercar", "Pantalla completa"]) assert.ok(env.button(name), name);
    assert.equal(env.host.querySelector('a[aria-label="Abrir original"]')?.getAttribute("href"), "blob:original-receipt");
  } finally { await env.cleanup(); }
});

test("an image source keeps the existing image and viewer controls", async () => {
  const env = await setup("image/png");
  try {
    assert.equal(env.host.querySelectorAll("iframe").length, 0);
    assert.ok(env.host.querySelector('img[alt="Recibo original"]'));
    assert.equal(env.host.querySelectorAll('[data-testid="receipt-viewer-toolbar"]').length, 1);
    assert.ok(env.button("Girar a la derecha"));
    assert.equal(env.button("Página siguiente"), null);
  } finally { await env.cleanup(); }
});

test("a multi-page PDF moves to page two and back using the same toolbar", async () => {
  const env = await setup("application/pdf");
  try {
    const next = env.button("Página siguiente");
    assert.ok(next);
    assert.equal(env.button("Página anterior")?.disabled, true);
    const firstWidth = env.host.querySelector("canvas")?.width;
    assert.ok(firstWidth && firstWidth > 0);
    await env.act(async () => next.click());
    await env.settle();
    assert.equal(env.host.querySelector("canvas")?.getAttribute("aria-label"), "Página 2");
    assert.ok(env.host.querySelector("canvas")!.width < firstWidth);
    assert.equal(env.button("Página siguiente")?.disabled, true);
    assert.equal(env.button("Página anterior")?.disabled, false);
    await env.act(async () => env.button("Página anterior")!.click());
    await env.settle();
    assert.equal(env.host.querySelector("canvas")?.getAttribute("aria-label"), "Página 1");
    assert.equal(env.host.querySelectorAll('[data-testid="receipt-viewer-toolbar"]').length, 1);
  } finally { await env.cleanup(); }
});
