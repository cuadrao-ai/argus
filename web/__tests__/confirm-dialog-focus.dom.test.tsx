import assert from "node:assert/strict";
import { afterAll, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/" });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

describe("the confirmation dialog", () => {
  test("Cancel and Confirm show the same keyboard focus ring as every Business button", async () => {
    const { createRoot } = await import("react-dom/client");
    const { ConfirmDialog } = await import("@/components/ui/ConfirmDialog");
    const { FOCUS_RING } = await import("@/components/business-app/foundation/presentation");
    const { primaryButtonClass, secondaryButtonClass, quietButtonClass } = await import("@/components/business-app/business-ui");
    const host = document.createElement("div");
    document.body.append(host);
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <ConfirmDialog isOpen title="Eliminar" description="Se quita." confirmLabel="Eliminar" cancelLabel="Cancelar" onCancel={() => {}} onConfirm={() => {}} />,
      ),
    );
    const buttons = [...document.querySelectorAll<HTMLButtonElement>('[role="alertdialog"] button')];
    assert.deepEqual(buttons.map((button) => button.textContent?.trim()), ["Cancelar", "Eliminar"]);
    for (const button of buttons) assert.ok(button.className.includes(FOCUS_RING), `${button.textContent} has the ring`);
    for (const owned of [primaryButtonClass, secondaryButtonClass, quietButtonClass]) assert.ok(owned.includes(FOCUS_RING));
    await act(async () => root.unmount());
  });
});
