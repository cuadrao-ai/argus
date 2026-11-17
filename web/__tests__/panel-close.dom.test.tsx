import assert from "node:assert/strict";
import { afterAll, afterEach, beforeAll, describe, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";

/**
 * Every dossier and side panel closes the same way, and AdaptivePanel is the one place that decides it:
 * a click on the page beside it, Escape and its X close it on a desktop; on a phone, where it covers the
 * page, its X and system back do. Every way out goes through the owner's own close, so edits the owner
 * holds are never dropped silently, and focus goes back to what opened the panel.
 */

beforeAll(() => {
  GlobalRegistrator.register({ url: "http://localhost/biz", width: 1280, height: 900 });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
afterAll(async () => {
  await GlobalRegistrator.unregister();
});

const unmounts: (() => Promise<void>)[] = [];
afterEach(async () => {
  while (unmounts.length) await unmounts.pop()!();
  document.body.innerHTML = "";
  const { resetOverlayStack } = await import("@/components/layout/overlayStack");
  resetOverlayStack();
});

async function mount({ modal, width = 1280 }: { modal: boolean; width?: number }) {
  (window as unknown as { happyDOM: { setViewport: (size: { width: number; height: number }) => void } }).happyDOM.setViewport({ width, height: 900 });
  const { act, useRef, useState } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const i18next = (await import("i18next")).default;
  const { I18nextProvider } = await import("react-i18next");
  const spanish = (await import("@/public/locales/es-419/common.json")).default;
  const AdaptivePanel = (await import("@/components/ui/AdaptivePanel")).default;
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "es-419", resources: { "es-419": { translation: spanish } }, interpolation: { escapeValue: false } });

  /** An owner the way the dossiers are written: the panel's close asks first while the owner holds an edit. */
  function Owner() {
    const [open, setOpen] = useState(false);
    const [draft, setDraft] = useState("");
    const [asking, setAsking] = useState(false);
    const opener = useRef<HTMLButtonElement>(null);
    const close = () => (draft ? setAsking(true) : setOpen(false));
    return (
      <main>
        <button ref={opener} type="button" data-testid="opener" onClick={() => setOpen(true)}>Ferretería La Esquina</button>
        <div data-testid="page-blank"><p data-testid="page-text">Bandeja</p></div>
        <button type="button" data-testid="page-control">Filtrar</button>
        {asking ? <p data-testid="asking">¿Descartar los cambios?</p> : null}
        {open ? (
          <AdaptivePanel modal={modal} width="record" title="Ferretería La Esquina" closeLabel="Cerrar" onClose={close} returnFocusRef={opener} snaps={["full"]} initialSnap="full">
            <label>Nombre <input data-testid="draft" value={draft} onChange={(event) => setDraft(event.target.value)} /></label>
            <p data-testid="panel-text">RNC 101-00000-1</p>
          </AdaptivePanel>
        ) : null}
      </main>
    );
  }

  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<I18nextProvider i18n={i18n}><Owner /></I18nextProvider>);
  });
  unmounts.push(() => act(async () => root.unmount()));

  const panel = () => document.querySelector<HTMLElement>('[data-testid="side-drawer"], [role="dialog"]');
  const get = (testId: string) => document.querySelector<HTMLElement>(`[data-testid="${testId}"]`)!;
  /** A real press: pointerdown where it starts, then the click the browser sends where it ends. */
  const press = async (down: Element, up: Element = down) => {
    await act(async () => {
      down.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, cancelable: true, button: 0 }));
      up.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }));
    });
  };
  const key = async (target: Element, claim = false) => {
    const event = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    if (claim) target.addEventListener("keydown", (pressed) => pressed.preventDefault(), { once: true });
    await act(async () => { target.dispatchEvent(event); });
  };
  const open = async () => {
    const opener = get("opener");
    opener.focus();
    await act(async () => opener.click());
    assert.ok(panel(), "the panel is open");
  };
  const type = async (value: string) => {
    const input = document.querySelector<HTMLInputElement>('[data-testid="draft"]')!;
    await act(async () => {
      input.focus();
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
  };
  const closeButton = () => [...panel()!.querySelectorAll<HTMLButtonElement>('button[aria-label="Cerrar"]')].at(-1)!;
  return { act, panel, get, press, key, open, type, closeButton };
}

describe("a dossier beside its list on a desktop", () => {
  test("a click on the page beside it closes it, and focus goes back to the row that opened it", async () => {
    const page = await mount({ modal: false });
    await page.open();
    await page.press(page.get("page-text"));
    assert.equal(page.panel(), null, "the dossier closed");
    assert.equal(document.activeElement, page.get("opener"), "focus is back on the row");
  });

  test("a click on a control beside it leaves it open: the control does its own job", async () => {
    const page = await mount({ modal: false });
    await page.open();
    await page.press(page.get("page-control"));
    assert.ok(page.panel(), "the dossier stays open");
    await page.press(page.get("opener"));
    assert.ok(page.panel(), "a row beside it swaps the record instead of closing it");
  });

  test("a press that starts inside and ends beside it, such as selecting text, does not close it", async () => {
    const page = await mount({ modal: false });
    await page.open();
    await page.press(page.get("panel-text"), page.get("page-text"));
    assert.ok(page.panel(), "the dossier stays open");
  });

  test("Escape closes it from inside or from the page beside it, and focus goes back to the row", async () => {
    const page = await mount({ modal: false });
    await page.open();
    await page.key(page.get("panel-text"));
    assert.equal(page.panel(), null, "Escape inside closes it");
    assert.equal(document.activeElement, page.get("opener"));
    await page.open();
    await page.key(page.get("page-control"));
    assert.equal(page.panel(), null, "Escape beside it closes it too");
  });

  test("an Escape something nearer claims stays with it, and the dossier stays open", async () => {
    const page = await mount({ modal: false });
    await page.open();
    await page.key(page.get("draft"), true);
    assert.ok(page.panel(), "an editor that took Escape keeps the dossier open");
    await page.key(page.get("page-control"), true);
    assert.ok(page.panel(), "so does a page control that took it");
  });

  test("a layer open above it answers Escape and the click beside it first", async () => {
    const page = await mount({ modal: false });
    await page.open();
    const { registerOverlayLayer, unregisterOverlayLayer } = await import("@/components/layout/overlayStack");
    let escapes = 0;
    registerOverlayLayer({ id: "confirm-above", containerRef: { current: null }, trapFocus: false, onEscape: () => { escapes += 1; } });
    await page.press(page.get("page-text"));
    assert.ok(page.panel(), "a click beside it while a layer is up leaves the dossier");
    await page.key(page.get("page-text"));
    assert.equal(escapes, 1, "the layer took Escape");
    assert.ok(page.panel(), "and the dossier stays open");
    unregisterOverlayLayer("confirm-above");
  });

  test("its X closes it, and focus goes back to the row", async () => {
    const page = await mount({ modal: false });
    await page.open();
    await page.act(async () => page.closeButton().click());
    assert.equal(page.panel(), null);
    assert.equal(document.activeElement, page.get("opener"));
  });

  test("with an unsaved edit, every way out asks the owner, and the dossier and the edit stay", async () => {
    const page = await mount({ modal: false });
    await page.open();
    await page.type("Otro nombre");
    await page.press(page.get("page-text"));
    assert.ok(page.get("asking"), "a click beside it asks");
    assert.ok(page.panel(), "and keeps the dossier");
    await page.key(page.get("panel-text"));
    assert.ok(page.panel(), "Escape asks too");
    await page.act(async () => page.closeButton().click());
    assert.ok(page.panel(), "so does the X");
    assert.equal(document.querySelector<HTMLInputElement>('[data-testid="draft"]')?.value, "Otro nombre", "the typed value stays");
  });
});

describe("a modal side panel on a desktop", () => {
  test("a click beside it and Escape close it, focus goes back to its opener, and an unsaved edit asks", async () => {
    const page = await mount({ modal: true });
    await page.open();
    const beside = page.panel()!.previousElementSibling!;
    await page.press(beside);
    assert.equal(page.panel(), null, "a click beside it closes it");
    assert.equal(document.activeElement, page.get("opener"));
    await page.open();
    await page.key(page.get("panel-text"));
    assert.equal(page.panel(), null, "Escape closes it");
    assert.equal(document.activeElement, page.get("opener"));
    await page.open();
    await page.type("Otro nombre");
    await page.press(page.panel()!.previousElementSibling!);
    assert.ok(page.get("asking"), "with an edit, a click beside it asks");
    assert.ok(page.panel(), "and keeps the panel");
  });
});

describe("a dossier on a phone", () => {
  test("it covers the page: a press on the page does not close it, its X and system back do", async () => {
    const page = await mount({ modal: false, width: 390 });
    await page.open();
    assert.equal(page.panel()?.getAttribute("role"), "dialog", "a phone shows the full sheet");
    await page.press(page.get("page-text"));
    assert.ok(page.panel(), "there is no outside to click");
    await page.act(async () => page.closeButton().click());
    assert.equal(page.panel(), null, "the X closes it");
    await page.open();
    await page.act(async () => { window.dispatchEvent(new PopStateEvent("popstate")); });
    assert.equal(page.panel(), null, "system back closes it");
  });

  test("with an unsaved edit, the X asks the owner first", async () => {
    const page = await mount({ modal: false, width: 390 });
    await page.open();
    await page.type("Otro nombre");
    await page.act(async () => page.closeButton().click());
    assert.ok(page.get("asking"), "the X asks");
    assert.ok(page.panel(), "and keeps the sheet");
  });
});
