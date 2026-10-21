import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { Switch } from "@/components/ui/Switch";
import { readStored } from "@/lib/browser-storage";
import { setSwitchLabelsShown } from "@/lib/switch-labels";

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

test("turning switch words off clears the words from every switch at once, a named pair included, and turning them on brings them back", async () => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const words = (id: string) => host.querySelector(`[data-testid="${id}"]`)?.textContent ?? "";
  try {
    await act(async () => root.render(<><Switch testId="plain" label="Memoria" checked onChange={() => {}} /><Switch testId="named" label="Leer" checked={false} onChange={() => {}} stateLabels={{ on: "Activo", off: "Apagado" }} /></>));
    assert.equal(words("plain"), "YesNo");
    assert.equal(words("named"), "ActivoApagado");

    await act(async () => setSwitchLabelsShown(false));
    assert.equal(words("plain"), "");
    assert.equal(words("named"), "");
    assert.equal(readStored("cuadrao:switch_labels"), "false");
    assert.equal(host.querySelector('[data-testid="plain"]')?.getAttribute("aria-label"), "Memoria", "the name stays for assistive tech");

    await act(async () => setSwitchLabelsShown(true));
    assert.equal(words("plain"), "YesNo");
    assert.equal(words("named"), "ActivoApagado");
    assert.equal(readStored("cuadrao:switch_labels"), "true");
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});
