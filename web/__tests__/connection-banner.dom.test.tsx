import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { ConnectionBanner, useOnline } from "@/components/ui/ConnectionBanner";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

beforeAll(() => {
  GlobalRegistrator.register();
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

function Shell() {
  return useOnline() ? null : <ConnectionBanner />;
}

test("going offline docks the banner, and coming back removes it", async () => {
  let online = true;
  Object.defineProperty(navigator, "onLine", { configurable: true, get: () => online });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  try {
    await act(async () => root.render(<Shell />));
    assert.equal(host.querySelector('[data-testid="connection-banner"]'), null);
    online = false;
    await act(async () => { window.dispatchEvent(new Event("offline")); });
    const banner = host.querySelector('[data-testid="connection-banner"]');
    assert.equal(banner?.getAttribute("role"), "status");
    online = true;
    await act(async () => { window.dispatchEvent(new Event("online")); });
    assert.equal(host.querySelector('[data-testid="connection-banner"]'), null);
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});

test("a failed confirm says so inside the alert, and the confirm button stays to try again", async () => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  try {
    await act(async () => root.render(<ConfirmDialog isOpen tone="primary" title="¿Cerrar octubre?" description="El mes queda de solo lectura." confirmLabel="Sí, cerrar el mes" cancelLabel="Volver" error="No pudimos cerrar el mes. Inténtalo de nuevo." onCancel={() => {}} onConfirm={() => {}} />));
    const error = document.querySelector('[data-testid="confirm-dialog-error"]');
    assert.equal(error?.getAttribute("role"), "alert");
    assert.match(error?.textContent ?? "", /No pudimos cerrar el mes/);
    assert.ok(document.querySelector('[data-testid="confirm-dialog-confirm"]'));
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});
