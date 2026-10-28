import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { Mail, Share } from "lucide-react";
import ActionMenu from "@/components/business-app/ActionMenu";

beforeAll(() => {
  GlobalRegistrator.register();
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

const emails = { id: "emails", label: "Ver correos", icon: Mail, run: () => {} };
const exportAll = { id: "export", label: "Exportar registros", icon: Share, run: () => {} };

function Menu({ actions }: { actions: (typeof emails)[] }) {
  return (
    <ActionMenu actions={actions} label="Más" placement="below-end" renderTrigger={({ ref, toggle }) => <button ref={ref} type="button" onClick={toggle}>Más</button>} />
  );
}

test("items that arrive while the menu is open keep focus on the item it was on, so Escape still closes it", async () => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  try {
    await act(async () => root.render(<Menu actions={[emails]} />));
    await act(async () => host.querySelector("button")!.click());
    const focused = document.activeElement;
    assert.equal(focused?.textContent, "Ver correos");
    await act(async () => root.render(<Menu actions={[exportAll, emails]} />));
    assert.equal(document.activeElement, focused, "the same item keeps focus");
    await act(async () => { document.activeElement!.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
    assert.equal(host.querySelector('[role="menu"]'), null);
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});

test("a menu left with no item closes and stays closed when an item returns", async () => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  try {
    await act(async () => root.render(<Menu actions={[exportAll]} />));
    await act(async () => host.querySelector("button")!.click());
    assert.ok(document.querySelector('[role="menu"]'));
    await act(async () => root.render(<Menu actions={[]} />));
    assert.equal(document.querySelector('[role="menu"]'), null);
    await act(async () => root.render(<Menu actions={[exportAll]} />));
    assert.equal(document.querySelector('[role="menu"]'), null, "no orphan menu reopens");
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});
