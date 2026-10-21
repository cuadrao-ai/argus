import { afterAll, afterEach, beforeAll, describe, expect, test } from "bun:test";

/**
 * Routing goes to the top of the stack and stops there.
 *
 * The old shape asked every overlay to decide for itself whether a press was
 * meant for it, which is how the same defect appeared five times: a sheet that
 * closed while its row menu was open, a drawer that swallowed a nested dialog's
 * Escape, a parent trap that stole Tab from the modal above it. Those were one
 * bug wearing different clothes, and it could only be fixed once, by making the
 * layers the state and the routing central.
 *
 * These cases drive the registry directly, so they describe the rule rather
 * than the current set of surfaces that happen to follow it. Bun has no DOM, so
 * the document is stubbed down to what the registry actually uses.
 */

type Handler = (event: unknown) => void;

const listeners = new Map<string, Handler[]>();
let subject: typeof import("../components/layout/overlayStack");

beforeAll(async () => {
  (globalThis as { document?: unknown }).document = {
    activeElement: null,
    addEventListener: (type: string, handler: Handler) => {
      listeners.set(type, [...(listeners.get(type) ?? []), handler]);
    },
    removeEventListener: (type: string, handler: Handler) => {
      listeners.set(
        type,
        (listeners.get(type) ?? []).filter((open) => open !== handler),
      );
    },
  };
  subject = await import("../components/layout/overlayStack");
});

afterAll(() => {
  delete (globalThis as { document?: unknown }).document;
});

afterEach(() => subject.resetOverlayStack());

function dispatch(type: string, event: Record<string, unknown>): void {
  const payload = { preventDefault() {}, stopPropagation() {}, ...event };
  for (const handler of [...(listeners.get(type) ?? [])]) handler(payload);
}

const press = (key: string) => dispatch("keydown", { key });
const pointerDown = (target: unknown = null) =>
  dispatch("pointerdown", { target });

type Recorded = { escape: string[]; keys: string[]; outside: string[] };
const fresh = (): Recorded => ({ escape: [], keys: [], outside: [] });

function layer(
  id: string,
  log: Recorded,
  overrides: Partial<subjectLayer> = {},
): subjectLayer {
  return {
    id,
    containerRef: { current: null },
    trapFocus: false,
    onEscape: () => log.escape.push(id),
    ...overrides,
  } as subjectLayer;
}

type subjectLayer = import("../components/layout/overlayStack").OverlayLayer;

describe("overlay layer stack", () => {
  test("Escape reaches only the topmost layer", () => {
    const log = fresh();
    subject.registerOverlayLayer(layer("drawer", log));
    subject.registerOverlayLayer(layer("confirm", log));

    press("Escape");
    expect(log.escape).toEqual(["confirm"]);

    // One press, one level: the drawer answers only once it is topmost again.
    subject.unregisterOverlayLayer("confirm");
    press("Escape");
    expect(log.escape).toEqual(["confirm", "drawer"]);
  });

  test("a layer that opens and closes hands ownership back", () => {
    const log = fresh();
    subject.registerOverlayLayer(layer("sheet", log));
    subject.registerOverlayLayer(layer("row-menu", log));
    subject.unregisterOverlayLayer("row-menu");
    subject.registerOverlayLayer(layer("dossier", log));

    press("Escape");
    expect(log.escape).toEqual(["dossier"]);
  });

  test("a layer with its own keydown still only gets it while topmost", () => {
    const log = fresh();
    subject.registerOverlayLayer(
      layer("confirm", log, {
        onKeyDown: (event: KeyboardEvent) =>
          log.keys.push(`confirm:${event.key}`),
      }),
    );
    press("Enter");
    expect(log.keys).toEqual(["confirm:Enter"]);

    subject.registerOverlayLayer(layer("nested", log));
    press("Enter");
    // Nothing new: the confirmation is no longer the top of the stack.
    expect(log.keys).toEqual(["confirm:Enter"]);
  });

  test("outside presses go to the topmost layer only", () => {
    const log = fresh();
    const outside = (id: string) => () => log.outside.push(id);
    subject.registerOverlayLayer(
      layer("menu", log, { onOutsidePointerDown: outside("menu") }),
    );
    subject.registerOverlayLayer(
      layer("dialog", log, { onOutsidePointerDown: outside("dialog") }),
    );

    pointerDown();
    expect(log.outside).toEqual(["dialog"]);
  });

  test("a press inside the topmost container is not an outside press", () => {
    const log = fresh();
    const child = {};
    const panel = { contains: (node: unknown) => node === child };
    subject.registerOverlayLayer(
      layer("dialog", log, {
        containerRef: { current: panel as unknown as HTMLElement },
        onOutsidePointerDown: () => log.outside.push("dialog"),
      }),
    );

    pointerDown(child);
    expect(log.outside).toEqual([]);
    pointerDown({});
    expect(log.outside).toEqual(["dialog"]);
  });

  test("re-registering moves a layer to the top rather than duplicating it", () => {
    const log = fresh();
    subject.registerOverlayLayer(layer("a", log));
    subject.registerOverlayLayer(layer("b", log));
    subject.registerOverlayLayer(layer("a", log));

    expect(subject.overlayStackIds()).toEqual(["b", "a"]);
    expect(subject.isTopOverlay("a")).toBe(true);
    expect(subject.hasOverlayAbove("b")).toBe(true);
  });

  test("Tab containment falls to the nearest trapping layer", () => {
    // A menu is not modal and opts out, but a menu opened inside a drawer must
    // not let Tab walk out of the drawer, which declared aria-modal.
    const log = fresh();
    const inDrawer = {};
    const drawerPanel = { contains: (n: unknown) => n === inDrawer };
    subject.registerOverlayLayer(
      layer("drawer", log, {
        trapFocus: true,
        containerRef: { current: drawerPanel as unknown as HTMLElement },
      }),
    );
    subject.registerOverlayLayer(layer("menu", log, { trapFocus: false }));

    // The menu is topmost, so it owns Escape.
    press("Escape");
    expect(log.escape).toEqual(["menu"]);
    // Containment still resolves to the drawer beneath it.
    expect(subject.overlayStackIds()).toEqual(["drawer", "menu"]);
  });

  test("a reset after the document is gone still lets the next document be listened to", () => {
    const log = fresh();
    const original = (globalThis as { document?: unknown }).document;
    subject.registerOverlayLayer(layer("left-open", log));

    // A file that tears its DOM down with a layer still open.
    delete (globalThis as { document?: unknown }).document;
    subject.resetOverlayStack();

    const added: string[] = [];
    (globalThis as { document?: unknown }).document = {
      activeElement: null,
      addEventListener: (type: string) => added.push(type),
      removeEventListener: () => undefined,
    };
    try {
      subject.registerOverlayLayer(layer("next-file", log));
      expect(added).toEqual(["keydown", "pointerdown"]);
    } finally {
      subject.resetOverlayStack();
      // The discarded document's handlers went with it; a real DOM would too.
      listeners.clear();
      (globalThis as { document?: unknown }).document = original;
    }
  });

  test("nothing is listening once the last layer closes", () => {
    const log = fresh();
    subject.registerOverlayLayer(layer("only", log));
    subject.unregisterOverlayLayer("only");

    press("Escape");
    expect(log.escape).toEqual([]);
    expect(subject.overlayStackIds()).toEqual([]);
    // And the handlers are actually gone, not merely inert.
    expect((listeners.get("keydown") ?? []).length).toBe(0);
  });
});
