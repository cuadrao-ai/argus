import assert from "node:assert/strict";
import { afterAll, beforeAll, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { Avatar, AvatarGroup, initialsOf } from "@/components/ui/Avatar";

beforeAll(() => {
  GlobalRegistrator.register();
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => { await GlobalRegistrator.unregister(); });

test("initials take the first and last word, or two letters of one word, or an email's name", () => {
  assert.equal(initialsOf("Lucía Ramírez"), "LR");
  assert.equal(initialsOf("María de los Ángeles Peña"), "MP");
  assert.equal(initialsOf("Marta"), "MA");
  assert.equal(initialsOf("contadora.luna@example.test"), "CL");
  assert.equal(initialsOf(""), "");
  assert.equal(initialsOf(null), "");
});

async function render(node: React.ReactNode) {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => root.render(node));
  return { host, close: async () => { await act(async () => root.unmount()); host.remove(); } };
}

test("a name gets initials on one stable tint; no name gets the person icon; pending is a dashed ring", async () => {
  const view = await render(<><Avatar name="Lucía Ramírez" testId="a" /><Avatar name="Lucía Ramírez" testId="b" /><Avatar name={null} testId="c" /><Avatar name="x@example.test" status="pending" testId="d" /></>);
  try {
    const [a, b, c, d] = ["a", "b", "c", "d"].map((id) => view.host.querySelector<HTMLElement>(`[data-testid="${id}"]`)!);
    assert.equal(a.textContent, "LR");
    assert.equal(a.style.backgroundColor, b.style.backgroundColor, "the same name keeps the same tint");
    assert.equal(c.dataset.avatar, "icon");
    assert.match(d.className, /border-dashed/);
    assert.equal(d.style.backgroundColor, "");
  } finally { await view.close(); }
});

test("a group shows up to its max and counts the rest as +N, named for assistive tech", async () => {
  const view = await render(<AvatarGroup label="5 personas" max={3} people={["Ana", "Beto", "Carla", "Dario", "Eva"].map((name) => ({ name }))} />);
  try {
    const group = view.host.querySelector('[role="img"]')!;
    assert.equal(group.getAttribute("aria-label"), "5 personas");
    assert.match(group.textContent ?? "", /\+2$/);
  } finally { await view.close(); }
});
