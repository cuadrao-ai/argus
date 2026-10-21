import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { Switch } from "@/components/ui/Switch";

beforeAll(() => {
  GlobalRegistrator.register();
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

test("every switch shows its state in words without being asked, and a screen named pair replaces them", async () => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  try {
    await act(async () => root.render(<><Switch testId="plain" label="Memoria" checked={false} onChange={() => {}} /><Switch testId="named" label="Leer" checked onChange={() => {}} stateLabels={{ on: "Activo", off: "Apagado" }} /></>));
    const plain = host.querySelector('[data-testid="plain"]')!;
    assert.match(plain.textContent ?? "", /Yes/);
    assert.match(plain.textContent ?? "", /No/);
    assert.match(host.querySelector('[data-testid="named"]')?.textContent ?? "", /Activo/);
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});
